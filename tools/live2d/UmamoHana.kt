// Uses the released Umamo codecs/evaluator; does not invent a CMO3/MOC3 binary writer.
import java.io.File
import kotlin.math.abs
import kotlin.math.ceil
import kotlin.math.cos
import kotlin.math.sin
import kotlin.math.sqrt
import kotlinx.serialization.json.*
import org.umamo.format.art.*
import org.umamo.format.psd.PsdReader
import org.umamo.format.png.PngCodec
import org.umamo.format.raster.RasterImage
import org.umamo.format.atlas.*
import org.umamo.format.cmo3.Cmo3
import org.umamo.format.cmo3.model.custom.CModelSource
import org.umamo.format.moc3.Moc3
import org.umamo.interop.art.*
import org.umamo.interop.cmo3.*
import org.umamo.interop.moc3.Moc3Sidecars
import org.umamo.interop.moc3.`import`.Moc3Import
import org.umamo.render.DecodedImage
import org.umamo.render.atlasCompositionOf
import org.umamo.render.atlasPlacementFromPack
import org.umamo.render.generatedPuppetTextures
import org.umamo.render.meshReserveByTile
import org.umamo.render.withTexturePagesFrom
import org.umamo.render.eval.CpuDeformationEvaluator
import org.umamo.render.eval.renderOrder
import org.umamo.runtime.model.*
import org.umamo.ui.model.PackedAtOpen
import org.umamo.edit.withAtlasRepack

fun JsonObject.string(key: String) = getValue(key).jsonPrimitive.content
fun JsonObject.number(key: String) = getValue(key).jsonPrimitive.float

// Straight-alpha mipmap filtering otherwise mixes opaque art with black transparent cut edges.
// Change only invisible RGB, never the source alpha or any visible pixel.
fun edgeRgb(image: RasterImage): RasterImage {
    val rgba=image.rgba.copyOf();val w=image.width;val h=image.height;val count=w*h
    val distance=ByteArray(count){-1};val queue=IntArray(count);var start=0;var end=0
    fun neighbors(i:Int,visit:(Int)->Unit){val x=i%w;val y=i/w;if(x>0)visit(i-1);if(x+1<w)visit(i+1);if(y>0)visit(i-w);if(y+1<h)visit(i+w)}
    for(i in 0 until count)if((rgba[i*4+3].toInt()and 255)>0){
        distance[i]=0
        var boundary=false;neighbors(i){j->if(rgba[j*4+3].toInt()==0)boundary=true}
        if(boundary)queue[end++]=i
    }
    while(start<end){val i=queue[start++];if(distance[i]>=32)continue
        neighbors(i){j->if(distance[j].toInt()<0){
            distance[j]=(distance[i]+1).toByte();for(c in 0..2)rgba[j*4+c]=rgba[i*4+c];queue[end++]=j
        }}
    }
    for(i in 0 until count){check(rgba[i*4+3]==image.rgba[i*4+3]);if(rgba[i*4+3].toInt()!=0)for(c in 0..2)check(rgba[i*4+c]==image.rgba[i*4+c])}
    return RasterImage(w,h,rgba)
}

// Traditional warp/rotation keys, not blend-shape features: Cubism 3.0 playback stays compatible.
val liveParameters = listOf(
    Parameter(ParameterId("ParamAngleX"),"고개 좌우",-30f,30f,0f), Parameter(ParameterId("ParamAngleY"),"고개 상하",-30f,30f,0f),
    Parameter(ParameterId("ParamEyeBallX"),"시선 좌우",-1f,1f,0f),Parameter(ParameterId("ParamEyeBallY"),"시선 상하",-1f,1f,0f),
    Parameter(ParameterId("ParamEyeLOpen"),"왼쪽 눈 뜨기",0f,1.2f,1f),Parameter(ParameterId("ParamEyeROpen"),"오른쪽 눈 뜨기",0f,1.2f,1f),
    Parameter(ParameterId("ParamEyeSmile"),"눈웃음",0f,1f,0f),Parameter(ParameterId("ParamMouthOpenY"),"입 벌리기",0f,1f,0f),
    Parameter(ParameterId("ParamMouthForm"),"입 표정",-1f,1f,0f),Parameter(ParameterId("ParamBrowForm"),"눈썹 표정",-1f,1f,0f),
    Parameter(ParameterId("ParamBrowY"),"눈썹 높이",-1f,1f,0f),Parameter(ParameterId("ParamTears"),"눈물",0f,1f,0f),
    Parameter(ParameterId("ParamBreath"),"호흡",0f,1f,0f),Parameter(ParameterId("ParamHairSwing"),"연결 머리 흔들림",-1f,1f,0f),
    Parameter(ParameterId("ParamTailSwing"),"연결 꼬리 흔들림",-1f,1f,0f),
    Parameter(ParameterId("ParamArmSwingVL"),"왼팔 연결 움직임",-1f,1f,0f),Parameter(ParameterId("ParamArmSwingVR"),"오른팔 연결 움직임",-1f,1f,0f)
)

fun attachLiveRig(source: PuppetModel): PuppetModel {
    val deformers=source.deformers.toMutableList()
    val boxes=mutableMapOf<String,FloatArray>()
    val headPivot=floatArrayOf(1960f,1064f);val bodyPivot=floatArrayOf(1932f,2020f);val rootPivot=floatArrayOf(1932f,3120f)
    fun axis(id:String,vararg keys:Float)=KeyformAxis(ParameterId(id),keys)
    fun <T> grid(axes:List<KeyformAxis>,form:(Map<String,Float>)->T):KeyformGrid<T> {
        val cells=mutableListOf<KeyformCell<T>>()
        fun visit(i:Int,coordinate:IntArray,values:Map<String,Float>){
            if(i==axes.size){cells.add(KeyformCell(coordinate.copyOf(),form(values)));return}
            for(k in axes[i].keys.indices){coordinate[i]=k;visit(i+1,coordinate,values+mapOf(axes[i].parameterId.raw to axes[i].keys[k]))}
        }
        visit(0,IntArray(axes.size),emptyMap());return KeyformGrid(axes,cells)
    }
    fun warp(id:String,parent:String,box:FloatArray,pivot:FloatArray,axes:List<KeyformAxis>,move:(Float,Float,Map<String,Float>)->Pair<Float,Float>){
        boxes[id]=box
        val rows=8;val cols=8
        val forms=grid(axes){ values ->
            val points=FloatArray((rows+1)*(cols+1)*2)
            for(y in 0..rows)for(x in 0..cols){
                val px=box[0]+box[2]*x/cols;val py=box[1]+box[3]*y/rows
                val (mx,my)=move(px,py,values);val i=(y*(cols+1)+x)*2;val pb=boxes[parent]
                points[i]=if(pb==null)mx-pivot[0] else (mx-pb[0])/pb[2]
                points[i+1]=if(pb==null)my-pivot[1] else (my-pb[1])/pb[3]
            }
            WarpLatticeForm(points)
        }
        deformers.add(Deformer.Warp(DeformerId(id),id,DeformerId(parent),null,rows,cols,false,forms))
    }
    fun smooth(t:Float):Float {val u=t.coerceIn(0f,1f);return u*u*(3-2*u)}
    warp("Live_Head","Hana_Head",floatArrayOf(1000f,-100f,1850f,1650f),headPivot,listOf(axis("ParamAngleX",-30f,0f,30f),axis("ParamAngleY",-30f,0f,30f))){x,y,v->
        val w=1-smooth((y-1030f)/200f)
        val yaw=v.getValue("ParamAngleX")*.012f;val pitch=v.getValue("ParamAngleY")*.010f
        val depth=235f*sqrt((1-((x-1955f)/670f)*((x-1955f)/670f)).coerceIn(.12f,1f))
        // Coordinated yaw/pitch projection; no yaw-induced diagonal shear or sliding facial fragments.
        Pair(x+w*((x-1955f)*(cos(yaw)-1)+sin(yaw)*depth),
             y+w*((y-710f)*(cos(pitch)-1)-sin(pitch)*depth))
    }
    warp("Live_Hair","Live_Head",floatArrayOf(1000f,-100f,1850f,1650f),headPivot,listOf(axis("ParamHairSwing",-1f,0f,1f))){x,y,v->
        // Keep the contact roots under the shoulder cape anchored; free curl tips still use the full swing.
        val nearCape=maxOf(1-smooth(abs(x-1460f)/210f),1-smooth(abs(x-2580f)/210f))
        val contact=nearCape*smooth((y-980f)/150f)*(1-smooth((y-1480f)/150f))
        Pair(x+v.getValue("ParamHairSwing")*35f*smooth((y-400f)/900f)*(1-contact),y)
    }
    warp("Live_Tail","Hana_Root",floatArrayOf(2350f,2660f,1740f,1900f),rootPivot,listOf(axis("ParamTailSwing",-1f,0f,1f))){x,y,v->
        val w=smooth((x-2370f)/1450f);val a=v.getValue("ParamTailSwing")
        Pair(x+a*50f*w,y-a*60f*w)
    }
    for(side in listOf("VL","VR")){
        val legBox=if(side=="VL")floatArrayOf(1200f,3050f,850f,2200f)else floatArrayOf(1900f,3050f,750f,2200f)
        warp("Live_Leg_$side","Hana_Root",legBox,rootPivot,listOf(axis("ParamLeg$side",-1f,0f,1f),axis("ParamKnee$side",-1f,0f,1f))){x,y,v->
            val upper=smooth((y-3200f)/1000f);val lower=smooth((y-4100f)/650f)
            val ankle=1-smooth((y-4800f)/250f)
            Pair(x+(v.getValue("ParamLeg$side")*20f*upper+v.getValue("ParamKnee$side")*15f*lower)*ankle,y)
        }
        val b=if(side=="VL")floatArrayOf(500f,1200f,1300f,2350f)else floatArrayOf(2280f,1200f,1300f,2350f)
        warp("Live_Arm_$side","Hana_Body",b,bodyPivot,listOf(axis("ParamArmSwing$side",-1f,0f,1f))){x,y,v->
            val w=smooth((y-1300f)/1800f);val a=v.getValue("ParamArmSwing$side")
            Pair(x+a*35f*w,y-abs(a)*7f*w)
        }
        val eye=if(side=="VL")floatArrayOf(1590f,730f,290f,170f)else floatArrayOf(1930f,635f,300f,200f)
        val xc=if(side=="VL")1777f else 2059f;val yc=if(side=="VL")818f else 754f;val slope=if(side=="VL")-.055f else -.20f
        val open="ParamEye${if(side=="VL")"L" else "R"}Open"
        warp("Live_Eye_$side","Live_Head",eye,headPivot,listOf(axis(open,0f,1f,1.2f),axis("ParamEyeSmile",0f,1f))){x,y,v->
            val o=v.getValue(open);val u=(x-xc)/130f
            val line=yc+slope*(x-xc)-(3f+v.getValue("ParamEyeSmile")*12f)*(1-u*u)
            Pair(x,line+(y-line)*(.04f+.96f*o))
        }
        warp("Live_Lashes_$side","Live_Head",eye,headPivot,listOf(axis(open,0f,1f,1.2f),axis("ParamEyeSmile",0f,1f))){x,y,v->
            val o=v.getValue(open);val u=(x-xc)/130f
            val closed=yc+slope*(x-xc)+(4f-v.getValue("ParamEyeSmile")*10f)*(1-u*u)+(y-yc+20f)*.24f
            Pair(x,closed+(y-closed)*o)
        }
        // A child rotation does not inherit a warp's pixel scale. Use a child warp for gaze translation.
        warp("Live_Gaze_$side","Live_Eye_$side",eye,headPivot,listOf(axis("ParamEyeBallX",-1f,0f,1f),axis("ParamEyeBallY",-1f,0f,1f))){x,y,v->
            Pair(x+v.getValue("ParamEyeBallX")*7f,y-v.getValue("ParamEyeBallY")*5f)
        }
        val brow=if(side=="VL")floatArrayOf(1651f,651f,117f,88f)else floatArrayOf(1945f,576f,141f,93f)
        warp("Live_Brow_$side","Live_Head",brow,headPivot,listOf(axis("ParamBrowForm",-1f,0f,1f),axis("ParamBrowY",-1f,0f,1f))){x,y,v->
            val direction=if(side=="VL")1f else -1f
            Pair(x,y+direction*v.getValue("ParamBrowForm")*.30f*(x-brow[0]-brow[2]/2)-v.getValue("ParamBrowY")*16f)
        }
    }
    val mouthBox=floatArrayOf(1855f,883f,182f,112f)
    for(open in listOf(false,true))warp(if(open)"Live_MouthOpen" else "Live_MouthClosed","Live_Head",mouthBox,headPivot,
        if(open)listOf(axis("ParamMouthOpenY",0f,.5f,1f),axis("ParamMouthForm",-1f,0f,1f))else listOf(axis("ParamMouthForm",-1f,0f,1f))){x,y,v->
        val f=v.getValue("ParamMouthForm");val u=(x-1946f)/65f
        val my=if(open)913f+(y-913f)*(.1f+.9f*v.getValue("ParamMouthOpenY")) else y
        Pair(1946f+(x-1946f)*(1+.12f*f),my+f*24f*(1-u*u))
    }
    val scalars=fun(id:String,keys:FloatArray,values:FloatArray):KeyformGrid<ChannelValue> =
        KeyformGrid(listOf(KeyformAxis(ParameterId(id),keys)),keys.indices.map{KeyformCell(intArrayOf(it),ChannelValue.Scalar(values[it]))})
    val ids=source.drawables.associate{it.name to it.id}
    val drawables=source.drawables.map{d->
        val name=d.name;var parent:String?=null;var box:FloatArray?=null;var channels=d.channelGrids;var masked=d.maskedBy
        when{
            name.startsWith("Tail_")->parent="Live_Tail"
            name.startsWith("Leg_")->parent="Live_Leg_${if(name.contains("_VL"))"VL" else "VR"}"
            Regex("^(Sleeve|ArmBand|Shoulder|Cuff|Hand)").containsMatchIn(name)->parent="Live_Arm_${if(name.contains("_VL"))"VL" else "VR"}"
            name.startsWith("Brow_")->parent="Live_Brow_${if(name.contains("_VL"))"VL" else "VR"}"
            name.startsWith("Mouth")->parent=if(name=="Mouth_Open")"Live_MouthOpen" else "Live_MouthClosed"
            name.startsWith("Eye_")&&!name.endsWith("_Tear")->{
                val side=if(name.contains("_VL"))"VL" else "VR";val iris=Regex("Iris|Pupil|Catchlight|Reflection").containsMatchIn(name)
                parent=if(iris)"Live_Gaze_$side" else if(name.endsWith("UpperLashes"))"Live_Lashes_$side" else "Live_Eye_$side"
                box=boxes.getValue("Live_Eye_$side")
                if(iris)masked=listOf(ids.getValue("Eye_${side}_Sclera"))
                if(iris||name.endsWith("Sclera"))channels=ChannelGrids(channels.gridsByChannel+mapOf(FormChannel.OPACITY to scalars("ParamEye${if(side=="VL")"L" else "R"}Open",floatArrayOf(0f,.08f,.12f,1f,1.2f),floatArrayOf(0f,0f,1f,1f,1f))))
                if(Regex("OuterCorner|LowerLid|UpperLid").containsMatchIn(name))channels=ChannelGrids(channels.gridsByChannel+mapOf(FormChannel.OPACITY to scalars("ParamEye${if(side=="VL")"L" else "R"}Open",floatArrayOf(0f,.2f,1f,1.2f),floatArrayOf(0f,1f,1f,1f))))
            }
            name.startsWith("Pony_")->parent="Live_Hair"
            Regex("^(Hair_|Forelock_)").containsMatchIn(name)->parent="Live_Head"
            name in listOf("Face","Neck","Nose")||name.startsWith("HairClip_")||name.endsWith("_Tear")->parent="Live_Head"
        }
        if(name.startsWith("Mouth"))channels=ChannelGrids(mapOf(FormChannel.OPACITY to scalars("ParamMouthOpenY",floatArrayOf(0f,.08f,.3f,1f),if(name=="Mouth_Open")floatArrayOf(0f,.5f,1f,1f)else floatArrayOf(1f,0f,0f,0f))))
        if(name.endsWith("_Tear"))channels=ChannelGrids(mapOf(FormChannel.OPACITY to scalars("ParamTears",floatArrayOf(0f,1f),floatArrayOf(0f,1f))))
        if(parent==null)d else{
            val rect=box?:boxes.getValue(parent);val mesh=d.mesh!!
            // Store normalized rest coordinates directly; subtracting large pixel positions loses precision.
            val normalized=FloatArray(mesh.positions.size){i->(mesh.positions[i]-rect[i%2])/rect[2+i%2]}
            d.copy(mesh=DrawableMesh(normalized,mesh.uvs,mesh.indices),parentDeformerId=DeformerId(parent),geometryGrid=KeyformGrid(listOf(axis("ParamRootZ",-1f,0f,1f)),(0..2).map{KeyformCell(intArrayOf(it),MeshDeltaForm(FloatArray(normalized.size)))}),channelGrids=channels,maskedBy=masked)
        }
    }
    val breathing=deformers.map{d->
        if(d.id.raw!="Hana_Body")d else (d as Deformer.Rotation).copy(geometryGrid=grid(listOf(axis("ParamBodyAngleZ",-10f,0f,10f),axis("ParamBreath",0f,1f))){v->
            val b=v.getValue("ParamBreath")
            RotationPivotForm(bodyPivot[0]-rootPivot[0],bodyPivot[1]-rootPivot[1]-2f*b,v.getValue("ParamBodyAngleZ")*.4f,1f+.0004f*b)
        })
    }
    return source.copy(drawables=drawables,deformers=breathing)
}

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
    val live=assignments.containsKey("Mouth_Open")
    val parameters = bones.distinctBy { it.string("parameter") }.map {
        Parameter(ParameterId(it.string("parameter")), it.string("id"), -it.number("inputRange"), it.number("inputRange"), 0f)
    } + if(live)liveParameters else emptyList()
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
        val nx = if(live&&d.name.startsWith("Mouth"))16 else if(live&&d.name.startsWith("Eye_"))12 else ceil(abs(quad.positions[2] - quad.positions[0]) / 100f).toInt().coerceIn(2, 24)
        val ny = if(live&&d.name.startsWith("Mouth"))8 else if(live&&d.name.startsWith("Eye_"))6 else ceil(abs(quad.positions[5] - quad.positions[1]) / 100f).toInt().coerceIn(2, 32)
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
    val initialModel = imported.puppet.copy(drawables=drawables, deformers=deformers, runtimeTarget=RuntimeTarget.Cubism53)
    val model = if(live)attachLiveRig(initialModel)else initialModel
    val eval = CpuDeformationEvaluator()
    val neutral = eval.evaluate(model, emptyMap())
    for (d in model.drawables) {
        val expected = originalMeshes.getValue(d.name).positions.copyOf()
        // The invisible open-mouth texture is deliberately collapsed at its closed key.
        if(live&&d.name=="Mouth_Open")for(i in 1 until expected.size step 2)expected[i]=913f+(expected[i]-913f)*.1f
        val actual = neutral.worldPositions.getValue(d.id)
        val maxError=actual.indices.maxOf{abs(actual[it]-if(it%2==0)expected[it]else -expected[it])}
        check(maxError < .02f) { "Neutral moved: ${d.name}; max error $maxError; expected ${expected.toList()}; actual ${actual.toList()}" }
    }
    println("Neutral-pose check: PASS; ${drawables.size} meshes, ${deformers.size} rotation deformers")
    val textures=imported.rasterByTile.mapValues{(_,r)->edgeRgb(RasterImage(r.width,r.height,r.rgba))}
    // Two-pixel editor gutters bleed at the app's 300 px display size (4K textures use mipmaps).
    val options=AtlasPackOptions(gutter=32,extrude=32)
    val reserves=meshReserveByTile(model)
    val atlas=packAtlas(model.atlas.tiles.map { t ->
        val r=textures.getValue(t.id);AtlasPackItem(t.id.raw,r.width,r.height,r.rgba,reserves[t.id])
    },options)
    check(atlas.skipped.isEmpty()) { "Atlas refused tiles: ${atlas.skipped}" }
    val placements=atlas.placements.associate { AtlasTileId(it.key) to atlasPlacementFromPack(it) }
    val repacked=model.withAtlasRepack(atlas.pages.map { AtlasPage(it.width,it.height) },placements,atlasCompositionOf(options))
    val packed=PackedAtOpen(repacked,generatedPuppetTextures(atlas.pages,repacked,false),emptyList())
    val pages = packed.textures.atlases.map { PngCodec.write(RasterImage(it.width,it.height,it.rgba)) }
    val cmo = Cmo3Conversion.freshCmo3(packed.model,
        packed.textures.atlases.mapIndexed { i,a -> Cmo3Conversion.AtlasPage(pages[i],a.width,a.height) },
        packed.textures.atlasIndexByDrawableId, "Hana", System.currentTimeMillis(), 47,
        tileRasters={ id -> textures[id] })
    check(cmo.report.notices.isEmpty()) { "CMO3 export notices: ${cmo.report.notices}" }
    val cmoBytes = Cmo3.write(cmo.model)
    val reopened = Cmo3Import.fromModelSource(Cmo3.read(cmoBytes).root as CModelSource)
    check(reopened.drawables.size == parts.size && reopened.deformers.size == model.deformers.size)
    checkPaintOrder(packed.model, "Packed model")
    checkPaintOrder(reopened, "Reopened CMO3")
    val poses = listOf(emptyMap(), mapOf(ParameterId("ParamAngleZ") to 30f), mapOf(ParameterId("ParamTailTip") to 1f)) +
        bones.map { mapOf(ParameterId(it.string("parameter")) to it.number("inputRange")) } +
        if(live)liveParameters.flatMap{listOf(mapOf(it.id to it.min),mapOf(it.id to it.max))}else emptyList()
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
    val bundle = Moc3Sidecars.bundle(withTexturePagesFrom(packed.model.copy(runtimeTarget=RuntimeTarget.Cubism30),packed.textures),"hana", pages=pages.mapIndexed { i,p -> Moc3Sidecars.AtlasPage("hana-textures/texture_$i.png",p) })
    check(bundle.report.notices.isEmpty()) { "MOC3 export notices: ${bundle.report.notices}" }
    val baked = Moc3Import.fromMocDocument(Moc3.read(bundle.files.first { it.name==bundle.mocFileName }.bytes),null)
    check(baked.drawables.size == drawables.size && baked.deformers.size == model.deformers.size)
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
        put("atlasGutterPixels",options.gutter)
        put("eyeBlinkGazeMouthKeys",live);put("warpDeformers",model.deformers.filterIsInstance<Deformer.Warp>().size)
        put("eyeBlinkGazeMouthPhysicsFinished",false);put("largeHiddenAnatomyRepainted",false)
    }
    File(folder,"qa/umamo-rig.json").writeText(Json { prettyPrint=true }.encodeToString(JsonObject.serializer(),report)+"\n")
    println(report)
}
