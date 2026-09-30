// Uses the released Umamo codecs/evaluator; does not invent a CMO3/MOC3 binary writer.
import java.io.File
import kotlin.math.abs
import kotlin.math.ceil
import kotlinx.serialization.json.*
import org.umamo.format.art.*
import org.umamo.format.psd.PsdReader
import org.umamo.format.png.PngCodec
import org.umamo.format.raster.RasterImage
import org.umamo.format.cmo3.Cmo3
import org.umamo.format.cmo3.model.custom.CModelSource
import org.umamo.format.moc3.Moc3
import org.umamo.interop.art.*
import org.umamo.interop.cmo3.*
import org.umamo.interop.moc3.Moc3Sidecars
import org.umamo.interop.moc3.`import`.Moc3Import
import org.umamo.render.DecodedImage
import org.umamo.render.withTexturePagesFrom
import org.umamo.render.eval.CpuDeformationEvaluator
import org.umamo.render.eval.renderOrder
import org.umamo.runtime.model.*
import org.umamo.ui.model.packModelAtOpen

fun JsonObject.string(key: String) = getValue(key).jsonPrimitive.content
fun JsonObject.number(key: String) = getValue(key).jsonPrimitive.float

fun main(args: Array<String>) {
    require(args.size == 1) { "Usage: UmamoHanaKt <hana-v7-rig directory>" }
    val folder = File(args[0]).canonicalFile
    val spec = Json.parseToJsonElement(File(folder, "rig.json").readText()).jsonObject
    val bones = spec.getValue("bones").jsonArray.map { it.jsonObject }
    val parts = spec.getValue("parts").jsonArray.map { it.jsonObject }
    val assignments = parts.associate { it.string("id") to it.string("bone") }
    val byBone = bones.associateBy { it.string("id") }
    fun pivot(b: JsonObject) = b.getValue("pivot").jsonArray.map { it.jsonPrimitive.float }
    val rawArt = PsdReader.read(File(folder, "hana-rig-source.psd").readBytes())
    // The hidden eye masters stay in the PSD; do not pack anchors or display unclipped iris discs.
    val art = object : SourceArt {
        override val widthPx = rawArt.widthPx
        override val heightPx = rawArt.heightPx
        override val groups = rawArt.groups.filterNot { it.name.startsWith("98_") || it.name.startsWith("99_") }
        override val layers = rawArt.layers.filter { it.name in assignments }
    }
    check(art.layers.size == assignments.size) { "PSD parts missing or duplicated" }
    val expectedPaintOrder = art.layers.map { it.name }
    fun checkPaintOrder(model: PuppetModel, label: String, names: Map<DrawableId, String> = model.drawables.associate { it.id to it.name }) {
        val actual = renderOrder(model.renderRoot, CpuDeformationEvaluator().evaluate(model, emptyMap()).drawOrder).map { names.getValue(it) }
        check(actual == expectedPaintOrder) { "$label changes PSD paint order" }
    }
    val parameters = bones.distinctBy { it.string("parameter") }.map {
        Parameter(ParameterId(it.string("parameter")), it.string("id"), -it.number("inputRange"), it.number("inputRange"), 0f)
    }
    val imported = SourceArtImport.fromSourceArt(art, ArtSourceDescriptor("hana-rig-source.psd", null, "psd"), SourceArtImportOptions(parameters = parameters))
    check(imported.notices.isEmpty()) { "Source import notices: ${imported.notices}" }
    val deformers = bones.map { b ->
        val parent = b["parent"]?.jsonPrimitive?.contentOrNull
        val p = pivot(b)
        val pp = parent?.let { pivot(byBone.getValue(it)) } ?: listOf(0f, 0f)
        val inputRange = b.number("inputRange")
        val keys = floatArrayOf(-inputRange, 0f, inputRange)
        val forms = (-1..1).mapIndexed { index, v -> KeyformCell(intArrayOf(index), RotationPivotForm(p[0] - pp[0], p[1] - pp[1], v * b.number("range"), 1f)) }
        Deformer.Rotation(DeformerId("Hana_" + b.string("id")), b.string("id"), parent?.let { DeformerId("Hana_" + it) }, null, 0f,
            KeyformGrid(listOf(KeyformAxis(ParameterId(b.string("parameter")), keys)), forms))
    }
    val originalMeshes = mutableMapOf<String, DrawableMesh>()
    val drawables = imported.puppet.drawables.map { d ->
        val quad = checkNotNull(d.mesh)
        // ponytail: regular subdivision supports the initial rotation rig; contour-tailored topology needs a separate art pass.
        val nx = ceil(abs(quad.positions[2] - quad.positions[0]) / 100f).toInt().coerceIn(2, 24)
        val ny = ceil(abs(quad.positions[5] - quad.positions[1]) / 100f).toInt().coerceIn(2, 32)
        val positions = mutableListOf<Float>(); val uvs = mutableListOf<Float>(); val triangles = mutableListOf<Int>()
        fun sample(a: FloatArray, u: Float, v: Float, axis: Int) =
            a[axis] * (1-u)*(1-v) + a[2+axis]*u*(1-v) + a[4+axis]*u*v + a[6+axis]*(1-u)*v
        for (y in 0..ny) for (x in 0..nx) {
            val u = x.toFloat()/nx; val v = y.toFloat()/ny
            for (axis in 0..1) { positions.add(sample(quad.positions,u,v,axis)); uvs.add(sample(quad.uvs,u,v,axis)) }
        }
        for (y in 0 until ny) for (x in 0 until nx) {
            val a=y*(nx+1)+x; val c=a+nx+1
            triangles.addAll(listOf(a,a+1,c+1,a,c+1,c))
        }
        val mesh = DrawableMesh(positions.toFloatArray(), uvs.toFloatArray(), triangles.toIntArray())
        originalMeshes[d.name] = mesh
        val b = byBone.getValue(assignments.getValue(d.name)); val p = pivot(b)
        val deltas = FloatArray(mesh.positions.size) { -p[it % 2] }
        val grid = KeyformGrid(listOf(KeyformAxis(ParameterId("ParamRootZ"), floatArrayOf(-1f,0f,1f))),
            (0..2).map { KeyformCell(intArrayOf(it), MeshDeltaForm(deltas.copyOf())) })
        d.copy(mesh=mesh, parentDeformerId=DeformerId("Hana_"+b.string("id")), geometryGrid=grid)
    }
    val model = imported.puppet.copy(drawables=drawables, deformers=deformers, runtimeTarget=RuntimeTarget.Cubism53)
    val eval = CpuDeformationEvaluator()
    val neutral = eval.evaluate(model, emptyMap())
    for (d in model.drawables) {
        val expected = originalMeshes.getValue(d.name).positions
        val actual = neutral.worldPositions.getValue(d.id)
        check(actual.indices.all { abs(actual[it] - if(it % 2 == 0) expected[it] else -expected[it]) < .02f }) { "Neutral moved: ${d.name}" }
    }
    println("Neutral-pose check: PASS; ${drawables.size} meshes, ${deformers.size} rotation deformers")
    val packed = packModelAtOpen(model) { id -> imported.rasterByTile[id]?.let { DecodedImage(it.rgba,it.width,it.height) } }
    check(packed.refusals.isEmpty()) { "Atlas refused tiles: ${packed.refusals}" }
    val pages = packed.textures.atlases.map { PngCodec.write(RasterImage(it.width,it.height,it.rgba)) }
    val cmo = Cmo3Conversion.freshCmo3(packed.model,
        packed.textures.atlases.mapIndexed { i,a -> Cmo3Conversion.AtlasPage(pages[i],a.width,a.height) },
        packed.textures.atlasIndexByDrawableId, "Hana", System.currentTimeMillis(), 47,
        tileRasters={ id -> imported.rasterByTile[id]?.let { RasterImage(it.width,it.height,it.rgba) } })
    check(cmo.report.notices.isEmpty()) { "CMO3 export notices: ${cmo.report.notices}" }
    val cmoBytes = Cmo3.write(cmo.model)
    val reopened = Cmo3Import.fromModelSource(Cmo3.read(cmoBytes).root as CModelSource)
    check(reopened.drawables.size == parts.size && reopened.deformers.size == bones.size)
    checkPaintOrder(packed.model, "Packed model")
    checkPaintOrder(reopened, "Reopened CMO3")
    val poses = listOf(emptyMap(), mapOf(ParameterId("ParamAngleZ") to 30f), mapOf(ParameterId("ParamTailTip") to 1f)) +
        bones.map { mapOf(ParameterId(it.string("parameter")) to it.number("inputRange")) }
    val poseErrors = poses.map { pose ->
        val before=eval.evaluate(packed.model,pose); val after=eval.evaluate(reopened,pose)
        reopened.drawables.maxOf { d ->
            val old=packed.model.drawables.first { it.name==d.name }; val a=before.worldPositions.getValue(old.id);val b=after.worldPositions.getValue(d.id)
            check(a.size==b.size); a.indices.maxOf { abs(a[it]-b[it]) }
        }
    }
    check(poseErrors.all { it < .1f }) { "Saved/reopened pose mismatch: $poseErrors" }
    val head=eval.evaluate(reopened,poses[1]); val rest=eval.evaluate(reopened,poses[0])
    check(head.worldPositions.any { (id,a) -> a.indices.any { abs(a[it]-rest.worldPositions.getValue(id)[it])>1f } }) { "Head parameter does not move" }
    val bundle = Moc3Sidecars.bundle(withTexturePagesFrom(packed.model,packed.textures),"hana", pages=pages.mapIndexed { i,p -> Moc3Sidecars.AtlasPage("hana-textures/texture_$i.png",p) })
    check(bundle.report.notices.isEmpty()) { "MOC3 export notices: ${bundle.report.notices}" }
    val baked = Moc3Import.fromMocDocument(Moc3.read(bundle.files.first { it.name==bundle.mocFileName }.bytes),null)
    check(baked.drawables.size == drawables.size && baked.deformers.size == deformers.size)
    // MOC3 without a CDI sidecar carries drawable IDs, not the editor's part names.
    checkPaintOrder(baked, "Decoded MOC3", packed.model.drawables.associate { it.id to it.name })
    val mocPoseErrors = poses.map { pose ->
        val a=eval.evaluate(packed.model,pose);val b=eval.evaluate(baked,pose)
        packed.model.drawables.maxOf { d ->
            val x=a.worldPositions.getValue(d.id);val y=b.worldPositions.getValue(d.id)
            check(x.size==y.size);x.indices.maxOf { abs(x[it]-y[it]) }
        }
    }
    check(mocPoseErrors.all { it < .1f }) { "MOC3 pose mismatch: $mocPoseErrors" }
    val output=File(folder,"umamo"); output.mkdirs()
    File(output,"hana.cmo3").writeBytes(cmoBytes)
    for (f in bundle.files) { val target=File(output,f.name).canonicalFile; check(target.toPath().startsWith(output.canonicalFile.toPath())); target.parentFile.mkdirs();target.writeBytes(f.bytes) }
    File(folder,"rig.json").writeText(Json { prettyPrint=true }.encodeToString(JsonObject.serializer(),
        JsonObject(spec + mapOf("nativeModelCreated" to JsonPrimitive(true), "nativeModelFile" to JsonPrimitive("umamo/hana.cmo3"))))+"\n")
    val report=buildJsonObject {
        put("tool","Umamo 0.3.0-dev");put("parts",drawables.size);put("rotationDeformers",deformers.size);put("parameters",parameters.size)
        put("meshVertices",drawables.sumOf { it.mesh!!.vertexCount });put("atlasPages",pages.size);put("cmo3ReadBack","PASS");put("moc3Decode","PASS")
        put("neutralPose","PASS");put("savedPoseMaxErrorPixels",poseErrors.max());put("editorVisualCheck",false);put("live2dRuntimeTested",false)
        put("moc3PoseMaxErrorPixels",mocPoseErrors.max())
        put("nativePaintOrder","PASS");put("savedPoseChecks",poses.size)
        put("eyeBlinkGazeMouthPhysicsFinished",false);put("largeHiddenAnatomyRepainted",false)
    }
    File(folder,"qa/umamo-rig.json").writeText(Json { prettyPrint=true }.encodeToString(JsonObject.serializer(),report)+"\n")
    println(report)
}
