if(new URLSearchParams(location.search).has('desktop')) document.body.classList.add('desktop');
const canvas = document.getElementById('view');
const meshCanvas = document.getElementById('mesh');
const context = canvas.getContext('2d');
const slider = document.getElementById('scale');
const nodeCount = simulation.points.length;
const faceCount = simulation.faces.length;
const isModal = simulation.summary.analysis === 'modal';
const isThermal = simulation.summary.analysis === 'thermal';
let thermalPicking=isThermal;
function setThermalStudyMode(active){thermalPicking=!!active;draw();}
let modeAnimation = false, modePhase = 1, phaseOverride = null, exportingGif = false;
let catMode = false;
const coordinates = new Float64Array(nodeCount * 3);
const deformation = new Float64Array(nodeCount * 3);
const deformed = new Float64Array(nodeCount * 3);
const magnitudes = new Float64Array(nodeCount);
const scalarRanges = [[0,0],[Infinity,-Infinity],[Infinity,-Infinity],[Infinity,-Infinity]];
const stressValues = new Float32Array(isThermal ? simulation.temperature_K.map(value=>value-273.15) : simulation.von_mises_Pa || nodeCount);
scalarRanges.push(isThermal ? [stressValues.reduce((m,v)=>Math.min(m,v),Infinity),stressValues.reduce((m,v)=>Math.max(m,v),-Infinity)] : [0,stressValues.reduce((maximum,value)=>Math.max(maximum,value),0)]);
const bounds = [[Infinity,-Infinity],[Infinity,-Infinity],[Infinity,-Infinity]];
for(let node=0;node<nodeCount;node++){
  const scalarVector=isThermal?simulation.heat_flux_W_m2[node]:simulation.displacement[node];
  magnitudes[node] = Math.hypot(...scalarVector);
  scalarRanges[0][1] = Math.max(scalarRanges[0][1],magnitudes[node]);
  for(let axis=0;axis<3;axis++){
    coordinates[node*3+axis] = simulation.points[node][axis];
    deformation[node*3+axis] = simulation.displacement[node][axis];
    bounds[axis][0] = Math.min(bounds[axis][0],coordinates[node*3+axis]);
    bounds[axis][1] = Math.max(bounds[axis][1],coordinates[node*3+axis]);
    scalarRanges[axis+1][0] = Math.min(scalarRanges[axis+1][0],scalarVector[axis]);
    scalarRanges[axis+1][1] = Math.max(scalarRanges[axis+1][1],scalarVector[axis]);
  }
}
const maximum = scalarRanges[0][1];
const center = bounds.map(bound=>(bound[0]+bound[1])/2);
const span = Math.max(...bounds.map(bound=>bound[1]-bound[0]));
const faceIndices = new Uint32Array(simulation.faces.flat());
const scalarBuffer = new Float32Array(nodeCount*4);
for(let node=0;node<nodeCount;node++){
  scalarBuffer.set([magnitudes[node],...(isThermal?simulation.heat_flux_W_m2[node]:simulation.displacement[node])],node*4);
}
let yaw=-0.45, pitch=-0.5, drag=null;
let viewportMode=simulation.summary.view==='mesh'?'mesh':'results';
let edgeVisibility=true, themeDark=!document.body.classList.contains('desktop');
let deformationOverride=isThermal?0:isModal && maximum ? span*0.1/maximum : null, resultComponent=isThermal?'stress':'magnitude';
let framePending=false, deformationDirty=true, fitRequested=true, colorDirty=true;
let factor=0, cameraZoom=1, panX=0, panY=0, depthScale=1;
let target=center.slice(), deformedBounds=bounds.map(bound=>bound.slice());
let projection=null, fallbackColors=[], fallbackDepth=new Float64Array(faceCount);
const fallbackOrder=Array.from({length:faceCount},(_,index)=>index);
const projected=new Float64Array(nodeCount*3);
let facePickMode=null, selectedFaces=new Set(), selectionDirty=true;
const facePickSets={support:new Set(),load:new Set()},facePickTouched={support:false,load:false};
const cadFaceIds=simulation.face_ids || [];
const availableFaceIds=[...new Set(cadFaceIds.filter(id=>Number.isInteger(id)&&id>0))];
function setFacePicking(mode, ids=[]){
  if(mode!==null && (!['support','load'].includes(mode)||cadFaceIds.length!==faceCount||!availableFaceIds.length))return false;
  facePickMode=mode;
  if(mode){facePickSets[mode]=new Set(ids.filter(id=>availableFaceIds.includes(id)));facePickTouched[mode]=false;selectedFaces=facePickSets[mode];}
  else{selectedFaces=new Set();facePickTouched.support=facePickTouched.load=false;}
  selectionDirty=true;deformationDirty=true;fitRequested=true;
  canvas.style.cursor=mode?'crosshair':'';draw();return true;
}
function switchFacePicking(mode){
  if(!facePickMode||!['support','load'].includes(mode))return false;
  facePickMode=mode;selectedFaces=facePickSets[mode];selectionDirty=true;draw();return true;
}
function clearPickedFaces(){if(facePickMode){selectedFaces.clear();facePickTouched[facePickMode]=true;selectionDirty=true;draw();}}
function getFaceSelection(){return {mode:facePickMode,support:[...facePickSets.support].sort((a,b)=>a-b),load:[...facePickSets.load].sort((a,b)=>a-b),touched:{...facePickTouched},available:availableFaceIds};}
function highlightedRole(face){
  if(!facePickMode)return null;
  const id=cadFaceIds[face];
  if(facePickSets[facePickMode].has(id))return facePickMode;
  const other=facePickMode==='support'?'load':'support';
  return facePickSets[other].has(id)?other:null;
}
function pickFaceAt(x,y){
  if(!facePickMode||!projection)return null;
  let nearest=-Infinity,hit=null;
  for(let face=0;face<faceCount;face++){
    const vertices=simulation.faces[face].map(node=>projection.project(coordinates.subarray(node*3,node*3+3)));
    const [a,b,c]=vertices,denominator=(b[1]-c[1])*(a[0]-c[0])+(c[0]-b[0])*(a[1]-c[1]);
    if(Math.abs(denominator)<1e-12)continue;
    const u=((b[1]-c[1])*(x-c[0])+(c[0]-b[0])*(y-c[1]))/denominator;
    const v=((c[1]-a[1])*(x-c[0])+(a[0]-c[0])*(y-c[1]))/denominator,w=1-u-v;
    if(u< -1e-8||v< -1e-8||w< -1e-8)continue;
    const depth=u*a[2]+v*b[2]+w*c[2];
    if(depth>nearest){nearest=depth;hit=cadFaceIds[face]||null;}
  }
  return hit;
}
function toggleFaceAt(x,y){
  const id=pickFaceAt(x,y);
  if(id!==null){selectedFaces.has(id)?selectedFaces.delete(id):selectedFaces.add(id);facePickTouched[facePickMode]=true;selectionDirty=true;draw();}
  return id;
}
const viewportStats=window.viewportStats={renderer:'canvas2d',frames:0,drawRequests:0,lastFrameMs:0,geometryUploads:0};

function createGpuRenderer(){
  selectionDirty=true;
  if(new URLSearchParams(location.search).has('canvas2d')) return null;
  const gpu=meshCanvas.getContext('webgl',{alpha:true,antialias:true,depth:true});
  if(!gpu) return null;
  try{
    const wideIndices=nodeCount>65535;
    if(wideIndices && !gpu.getExtension('OES_element_index_uint')) return null;
    function shader(type,source){
      const compiled=gpu.createShader(type);gpu.shaderSource(compiled,source);gpu.compileShader(compiled);
      if(!gpu.getShaderParameter(compiled,gpu.COMPILE_STATUS)) throw new Error(gpu.getShaderInfoLog(compiled));
      return compiled;
    }
    const program=gpu.createProgram();
    gpu.attachShader(program,shader(gpu.VERTEX_SHADER,`
      attribute vec3 position;attribute vec3 displacement;attribute vec4 values;attribute float stressValue;
      uniform mat4 projection;uniform vec3 target;uniform float deformationScale;uniform vec4 component;uniform float stressWeight;
      varying float scalar;
      void main(){gl_Position=projection*vec4(position+deformationScale*displacement-target,1.0);scalar=dot(values,component)+stressValue*stressWeight;}
    `));
    gpu.attachShader(program,shader(gpu.FRAGMENT_SHADER,`
      precision highp float;varying float scalar;
      uniform vec2 range;uniform bool results;uniform bool edges;uniform vec4 edgeColor;uniform vec3 solidColor;
      void main(){
        if(edges){gl_FragColor=edgeColor;return;}
        if(!results){gl_FragColor=vec4(solidColor,1.0);return;}
        float fraction=range.y>range.x?clamp((scalar-range.x)/(range.y-range.x),0.0,1.0):0.0;
        float hue=0.625*(1.0-fraction);
        vec3 chroma=clamp(abs(mod(hue*6.0+vec3(0.0,4.0,2.0),6.0)-3.0)-1.0,0.0,1.0);
        gl_FragColor=vec4(vec3(0.57)+(chroma-0.5)*0.645,1.0);
      }
    `));
    gpu.linkProgram(program);
    if(!gpu.getProgramParameter(program,gpu.LINK_STATUS)) throw new Error(gpu.getProgramInfoLog(program));
    gpu.useProgram(program);
    function attribute(name,width,data){
      const buffer=gpu.createBuffer();gpu.bindBuffer(gpu.ARRAY_BUFFER,buffer);gpu.bufferData(gpu.ARRAY_BUFFER,data,gpu.STATIC_DRAW);
      const location=gpu.getAttribLocation(program,name);gpu.enableVertexAttribArray(location);gpu.vertexAttribPointer(location,width,gpu.FLOAT,false,0,0);
    }
    const positions=new Float32Array(nodeCount*3),displacements=new Float32Array(deformation);
    for(let node=0;node<nodeCount;node++)for(let axis=0;axis<3;axis++)positions[node*3+axis]=coordinates[node*3+axis]-center[axis];
    attribute('position',3,positions);attribute('displacement',3,displacements);attribute('values',4,scalarBuffer);
    attribute('stressValue',1,stressValues);
    const IndexType=wideIndices?Uint32Array:Uint16Array;
    function indexBuffer(data){const buffer=gpu.createBuffer();gpu.bindBuffer(gpu.ELEMENT_ARRAY_BUFFER,buffer);gpu.bufferData(gpu.ELEMENT_ARRAY_BUFFER,new IndexType(data),gpu.STATIC_DRAW);return buffer;}
    const triangles=indexBuffer(faceIndices);
    const lineIndices=new IndexType(faceCount*6);
    for(let face=0;face<faceCount;face++){
      const first=faceIndices[face*3],second=faceIndices[face*3+1],third=faceIndices[face*3+2];
      lineIndices.set([first,second,second,third,third,first],face*6);
    }
    const lines=indexBuffer(lineIndices);
    const selections={support:{buffer:indexBuffer([]),count:0},load:{buffer:indexBuffer([]),count:0}};
    const uniforms=Object.fromEntries(['projection','target','deformationScale','component','stressWeight','range','results','edges','edgeColor','solidColor'].map(name=>[name,gpu.getUniformLocation(program,name)]));
    gpu.enable(gpu.DEPTH_TEST);gpu.depthFunc(gpu.LEQUAL);gpu.clearColor(0,0,0,0);
    viewportStats.geometryUploads++;
    return {draw(matrix){
      gpu.viewport(0,0,meshCanvas.width,meshCanvas.height);gpu.clear(gpu.COLOR_BUFFER_BIT|gpu.DEPTH_BUFFER_BIT);
      gpu.useProgram(program);gpu.uniformMatrix4fv(uniforms.projection,false,matrix);
      gpu.uniform3fv(uniforms.target,target.map((value,axis)=>value-center[axis]));
      gpu.uniform1f(uniforms.deformationScale,factor*modePhase);
      const component=[0,0,0,0];if(componentIndex()<4)component[componentIndex()]=1;gpu.uniform4fv(uniforms.component,component);
      gpu.uniform1f(uniforms.stressWeight,resultComponent==='stress'?1:0);
      gpu.uniform2fv(uniforms.range,scalarRanges[componentIndex()]);gpu.uniform1i(uniforms.results,viewportMode==='results'&&!facePickMode);
      gpu.uniform3fv(uniforms.solidColor,themeDark?[0.44,0.55,0.68]:[0.68,0.75,0.82]);
      gpu.uniform1i(uniforms.edges,false);gpu.enable(gpu.POLYGON_OFFSET_FILL);gpu.polygonOffset(1,1);
      gpu.bindBuffer(gpu.ELEMENT_ARRAY_BUFFER,triangles);gpu.drawElements(gpu.TRIANGLES,faceCount*3,wideIndices?gpu.UNSIGNED_INT:gpu.UNSIGNED_SHORT,0);
      gpu.disable(gpu.POLYGON_OFFSET_FILL);
      if(selectionDirty){
        for(const role of ['support','load']){
          const indices=[];
          for(let face=0;face<faceCount;face++)if(highlightedRole(face)===role)indices.push(...simulation.faces[face]);
          gpu.bindBuffer(gpu.ELEMENT_ARRAY_BUFFER,selections[role].buffer);gpu.bufferData(gpu.ELEMENT_ARRAY_BUFFER,new IndexType(indices),gpu.DYNAMIC_DRAW);
          selections[role].count=indices.length;
        }
        selectionDirty=false;
      }
      for(const role of ['support','load'])if(facePickMode && selections[role].count){
        gpu.uniform1i(uniforms.results,false);gpu.uniform1i(uniforms.edges,false);
        gpu.uniform3fv(uniforms.solidColor,role==='support'?[0.1,0.85,0.9]:[1,0.65,0.12]);
        gpu.enable(gpu.POLYGON_OFFSET_FILL);gpu.polygonOffset(-2,-2);
        gpu.bindBuffer(gpu.ELEMENT_ARRAY_BUFFER,selections[role].buffer);gpu.drawElements(gpu.TRIANGLES,selections[role].count,wideIndices?gpu.UNSIGNED_INT:gpu.UNSIGNED_SHORT,0);
        gpu.disable(gpu.POLYGON_OFFSET_FILL);
      }
      if(edgeVisibility && viewportMode!=='geometry'){
        gpu.enable(gpu.BLEND);gpu.blendFuncSeparate(gpu.SRC_ALPHA,gpu.ONE_MINUS_SRC_ALPHA,gpu.ONE,gpu.ONE_MINUS_SRC_ALPHA);
        gpu.uniform1i(uniforms.edges,true);gpu.uniform4fv(uniforms.edgeColor,themeDark?[0.7,0.82,0.95,0.2]:[0.19,0.28,0.36,0.4]);
        gpu.bindBuffer(gpu.ELEMENT_ARRAY_BUFFER,lines);gpu.drawElements(gpu.LINES,faceCount*6,wideIndices?gpu.UNSIGNED_INT:gpu.UNSIGNED_SHORT,0);
        gpu.disable(gpu.BLEND);
      }
    }};
  }catch(error){viewportStats.gpuError=String(error);return null;}
}
let gpuRenderer=createGpuRenderer();
viewportStats.renderer=gpuRenderer?'webgl':'canvas2d';
meshCanvas.style.display=gpuRenderer?'block':'none';
meshCanvas.addEventListener('webglcontextlost',event=>{event.preventDefault();gpuRenderer=null;meshCanvas.style.display='none';viewportStats.renderer='canvas2d';colorDirty=true;draw();});
meshCanvas.addEventListener('webglcontextrestored',()=>{gpuRenderer=createGpuRenderer();viewportStats.renderer=gpuRenderer?'webgl':'canvas2d';meshCanvas.style.display=gpuRenderer?'block':'none';draw();});

function componentIndex(){return resultComponent==='stress'?4:resultComponent==='magnitude'?0:'xyz'.indexOf(resultComponent)+1;}
function setTheme(theme){themeDark=theme==='dark'||theme==='midnight';document.body.classList.toggle('dark',themeDark);document.body.classList.toggle('midnight',theme==='midnight');draw();}
function setCatMode(value){catMode=Boolean(value);draw();}
function setResultComponent(component){if(!['magnitude','x','y','z','stress'].includes(component))return;resultComponent=component==='stress'&&!simulation.von_mises_Pa&&!isThermal?'magnitude':component;colorDirty=true;draw();}
function setViewportMode(mode){if(mode==='modal')mode='results';if(viewportMode!==mode){viewportMode=mode;deformationDirty=true;fitRequested=true;}draw();}
function setModeAnimation(value){modeAnimation=isModal && Boolean(value);if(!modeAnimation)modePhase=1;draw();}
function setEdgeVisibility(value){edgeVisibility=Boolean(value);draw();}
function setDeformationScale(value){deformationOverride=isThermal?0:value==='auto'?(maximum?span*0.1/maximum:0):Number(value);deformationDirty=true;fitRequested=true;draw();}
function resetViewport(){panX=panY=0;fitRequested=true;draw();}
function setViewOrientation(orientation){yaw=orientation==='flipped-front'?Math.PI:orientation==='isometric'?-0.45:0;pitch=orientation==='flipped-front'?Math.PI:orientation==='front'?0:orientation==='top'?-Math.PI/2:-0.5;panX=panY=0;fitRequested=true;draw();}
function draw(){
  viewportStats.drawRequests++;
  if(framePending)return;
  framePending=true;
  requestAnimationFrame(()=>{framePending=false;renderFrame();});
}
function updateDeformation(){
  factor=viewportMode==='results'&&!facePickMode?(deformationOverride??Number(slider.value)):0;
  deformedBounds=[[Infinity,-Infinity],[Infinity,-Infinity],[Infinity,-Infinity]];
  for(let node=0;node<nodeCount;node++)for(let axis=0;axis<3;axis++){
    const value=coordinates[node*3+axis]+factor*deformation[node*3+axis];deformed[node*3+axis]=value;
    const amplitude=isModal?Math.abs(factor*deformation[node*3+axis]):0;
    deformedBounds[axis][0]=Math.min(deformedBounds[axis][0],isModal?coordinates[node*3+axis]-amplitude:value);
    deformedBounds[axis][1]=Math.max(deformedBounds[axis][1],isModal?coordinates[node*3+axis]+amplitude:value);
  }
  target=deformedBounds.map(bound=>(bound[0]+bound[1])/2);
  depthScale=Math.max(span*0.01,Math.hypot(...deformedBounds.map(bound=>(bound[1]-bound[0])/2))*1.2);
  deformationDirty=false;
}
function cameraProjection(){
  const cosineYaw=Math.cos(yaw),sineYaw=Math.sin(yaw),cosinePitch=Math.cos(pitch),sinePitch=Math.sin(pitch);
  function rotate(first,second,third){
    const relative=[first-target[0],second-target[1],third-target[2]];
    const depth=relative[0]*sineYaw+relative[1]*cosineYaw;
    // Screen right, screen down, toward the viewer. This must be a proper rotation (right-handed); an earlier
    // version used the opposite toward-viewer sign, which showed a mirror image seen from the far side.
    return [relative[0]*cosineYaw-relative[1]*sineYaw,depth*sinePitch-relative[2]*cosinePitch,-(depth*cosinePitch+relative[2]*sinePitch)];
  }
  if(fitRequested){
    let minHorizontal=Infinity,maxHorizontal=-Infinity,minVertical=Infinity,maxVertical=-Infinity;
    for(let corner=0;corner<8;corner++){
      const point=rotate(deformedBounds[0][corner&1],deformedBounds[1][(corner>>1)&1],deformedBounds[2][(corner>>2)&1]);
      minHorizontal=Math.min(minHorizontal,point[0]);maxHorizontal=Math.max(maxHorizontal,point[0]);minVertical=Math.min(minVertical,point[1]);maxVertical=Math.max(maxVertical,point[1]);
    }
    cameraZoom=Math.min(Math.max(50,canvas.width-240*devicePixelRatio)/Math.max(maxHorizontal-minHorizontal,span*0.01),Math.max(50,canvas.height-160*devicePixelRatio)/Math.max(maxVertical-minVertical,span*0.01))*0.88;
    fitRequested=false;
  }
  const offset=[canvas.width/2-55*devicePixelRatio+panX,canvas.height/2+15*devicePixelRatio+panY];
  const horizontalScale=2*cameraZoom/canvas.width,verticalScale=2*cameraZoom/canvas.height;
  const matrix=new Float32Array([
    horizontalScale*cosineYaw,-verticalScale*sinePitch*sineYaw,cosinePitch*sineYaw/depthScale,0,
    -horizontalScale*sineYaw,-verticalScale*sinePitch*cosineYaw,cosinePitch*cosineYaw/depthScale,0,
    0,verticalScale*cosinePitch,sinePitch/depthScale,0,
    2*offset[0]/canvas.width-1,1-2*offset[1]/canvas.height,0,1
  ]);
  return {matrix,project(point){const rotated=rotate(point[0],point[1],point[2]);return [offset[0]+rotated[0]*cameraZoom,offset[1]+rotated[1]*cameraZoom,rotated[2]];}};
}
function drawFallback(){
  const component=componentIndex(),range=scalarRanges[component];
  if(colorDirty){
    fallbackColors=Array.from({length:faceCount},(_,face)=>{
      let average=0;for(let corner=0;corner<3;corner++){const node=faceIndices[face*3+corner];average+=(component===4?stressValues[node]:scalarBuffer[node*4+component])/3;}
      const fraction=range[1]>range[0]?(average-range[0])/(range[1]-range[0]):0;
      return `hsl(${225*(1-fraction)} 75% 57%)`;
    });colorDirty=false;
  }
  for(let node=0;node<nodeCount;node++){
    const point=isModal?[0,1,2].map(axis=>coordinates[node*3+axis]+factor*modePhase*deformation[node*3+axis]):deformed.subarray(node*3,node*3+3);
    projected.set(projection.project(point),node*3);
  }
  for(let face=0;face<faceCount;face++)fallbackDepth[face]=projected[faceIndices[face*3]*3+2]+projected[faceIndices[face*3+1]*3+2]+projected[faceIndices[face*3+2]*3+2];
  fallbackOrder.sort((left,right)=>fallbackDepth[left]-fallbackDepth[right]);
  context.strokeStyle=themeDark?'#b2d2f333':'#31485d66';context.lineWidth=0.5*devicePixelRatio;
  for(const face of fallbackOrder){
    const first=faceIndices[face*3]*3,second=faceIndices[face*3+1]*3,third=faceIndices[face*3+2]*3;
    context.beginPath();context.moveTo(projected[first],projected[first+1]);context.lineTo(projected[second],projected[second+1]);context.lineTo(projected[third],projected[third+1]);context.closePath();
    const role=highlightedRole(face);
    context.fillStyle=role?(role==='support'?'#1ad9e6':'#ffa61f'):viewportMode==='results'&&!facePickMode?fallbackColors[face]:(themeDark?'#718cae':'#aebed0');context.fill();
    if(edgeVisibility && viewportMode!=='geometry' && !drag)context.stroke();
  }
}
const AXIS_COLORS={light:['#d6262f','#1c8a3c','#1f5fd6'],dark:['#ff5c62','#4fd17a','#5c9dff']};
function axisTriad(){
  // Derived from the model's own projection so the triad always matches what is drawn.
  // screen = [right, down] per unit length; toward > 0 points at the viewer.
  const origin=projection.project(target);
  return [0,1,2].map(index=>{
    const point=projection.project(target.map((value,axis)=>value+(axis===index?1:0)));
    return {axis:'XYZ'[index],screen:[(point[0]-origin[0])/cameraZoom,(point[1]-origin[1])/cameraZoom],toward:point[2]-origin[2]};
  });
}
function drawAxisTriad(){
  const pixel=devicePixelRatio,length=34*pixel,radius=48*pixel;
  const origin=[18*pixel+radius,canvas.height-18*pixel-radius];
  const colors=AXIS_COLORS[themeDark?'dark':'light'];
  context.save();
  const axes=axisTriad();
  viewportStats.axisTriad=Object.fromEntries(axes.map(entry=>[entry.axis,{screen:entry.screen,toward:entry.toward}]));
  context.lineCap='round';context.textAlign='center';context.textBaseline='middle';
  context.font=`bold ${12*pixel}px Segoe UI`;
  // Far axes first so the one pointing at the viewer is drawn on top.
  for(const entry of axes.slice().sort((left,right)=>left.toward-right.toward)){
    const color=colors['XYZ'.indexOf(entry.axis)],[dx,dy]=entry.screen,projectedLength=Math.hypot(dx,dy);
    const tip=[origin[0]+dx*length,origin[1]+dy*length];
    context.globalAlpha=entry.toward< -0.2?0.55:1;
    context.strokeStyle=color;context.fillStyle=color;context.lineWidth=3*pixel;
    context.beginPath();context.moveTo(...origin);context.lineTo(...tip);context.stroke();
    if(projectedLength>0.15){
      const unit=[dx/projectedLength,dy/projectedLength],head=8*pixel,wing=4.5*pixel;
      context.beginPath();context.moveTo(tip[0]+unit[0]*head*0.6,tip[1]+unit[1]*head*0.6);
      context.lineTo(tip[0]-unit[0]*head*0.4-unit[1]*wing,tip[1]-unit[1]*head*0.4+unit[0]*wing);
      context.lineTo(tip[0]-unit[0]*head*0.4+unit[1]*wing,tip[1]-unit[1]*head*0.4-unit[0]*wing);context.closePath();context.fill();
    }else{
      // Axis points straight at or away from the viewer: dot for toward, ring for away.
      context.beginPath();context.arc(...origin,5*pixel,0,2*Math.PI);entry.toward>0?context.fill():context.stroke();
    }
    const label=projectedLength>0.15?[tip[0]+dx/projectedLength*13*pixel,tip[1]+dy/projectedLength*13*pixel]:[origin[0]+13*pixel,origin[1]-13*pixel];
    context.fillText(entry.axis,...label);
  }
  context.globalAlpha=1;context.fillStyle=themeDark?'#c6d7ec':'#34485f';
  context.beginPath();context.arc(...origin,2.5*pixel,0,2*Math.PI);context.fill();
  context.restore();
}
function drawOverlay(){
  drawAxisTriad();
  const pixel=devicePixelRatio,range=scalarRanges[componentIndex()];
  context.font=`${12*pixel}px Segoe UI`;context.fillStyle=themeDark?'#bbd2ec':'#3a506b';
  context.fillText(`${simulation.summary.element_type||'Tetrahedra'} · ${faceCount.toLocaleString()} ${catMode?'tiny triangle beans':'surface triangles'}${exportingGif?'':' · '+(gpuRenderer?'WebGL':'Canvas fallback')}`,20*pixel,27*pixel);
  if(facePickMode){
    context.fillStyle=facePickMode==='support'?'#1ad9e6':'#ffa61f';
    context.fillText(`Pick ${thermalPicking?(facePickMode==='support'?'fixed temperature (cyan)':'temperature / heat input (orange)'):(facePickMode==='support'?'fixed support (cyan)':'force faces (orange)')} · ${selectedFaces.size} face(s) · click to toggle`,20*pixel,48*pixel);
    context.fillText(`Draft: ${facePickSets.support.size} support / ${facePickSets.load.size} load faces · drag to rotate · Save picked faces to apply`,20*pixel,68*pixel);
    return;
  }
  if(viewportMode==='results'){
    context.fillText(isThermal?'Steady thermal conduction · undeformed geometry':isModal?`${catMode?'Wiggle':'Mode'} ${simulation.summary.mode_number} · ${simulation.summary.frequency_Hz.toPrecision(6)} Hz · ${catMode?'purr shape · dance speed':'normalized shape · playback'} ${exportingGif?'slowed to about 1 cycle per second':'1 Hz'}`:`${catMode?'Wiggle exaggeration':'Deformation display'}: ${factor.toPrecision(3)}×`,20*pixel,46*pixel);
    const gradient=context.createLinearGradient(0,75*pixel,0,210*pixel);
    for(let stop=0;stop<=6;stop++)gradient.addColorStop(stop/6,`hsl(${225*stop/6} 75% 57%)`);
    context.fillStyle=gradient;context.fillRect(canvas.width-112*pixel,75*pixel,14*pixel,135*pixel);
    const units=isThermal?(resultComponent==='stress'?'(°C)':'(W/m²)'):resultComponent==='stress'?'(MPa)':isModal?'(norm.)':'(mm)',unitScale=isThermal?1:resultComponent==='stress'?1e-6:isModal?1:1000;
    context.fillStyle=themeDark?'#c6d7ec':'#34485f';context.fillText((isThermal?(resultComponent==='stress'?'Temperature':resultComponent==='magnitude'?'|q|':`q${resultComponent}`):resultComponent==='stress'?'von Mises':resultComponent==='magnitude'?'|U|':`U${resultComponent}`)+' '+units,canvas.width-150*pixel,58*pixel);
    context.fillText((range[1]*unitScale).toPrecision(4),canvas.width-92*pixel,85*pixel);context.fillText((range[0]*unitScale).toPrecision(4),canvas.width-92*pixel,210*pixel);
  }
  if(isThermal)return;
  const anchor=projection.project(simulation.summary.support_point_m || [bounds[0][0],center[1],center[2]]);
  context.fillStyle=themeDark?'#41c8d6':'#087f8c';context.beginPath();context.arc(anchor[0],anchor[1],4*pixel,0,2*Math.PI);context.fill();context.fillText(catMode?'NO ZOOMIES':'FIXED',anchor[0]-15*pixel,anchor[1]+25*pixel);
  if(simulation.summary.load_point_m){
    const markers=simulation.summary.load_markers||[{point_m:simulation.summary.load_point_m,displacement_m:simulation.summary.load_point_displacement_m||[0,0,0]}];
    for(let markerIndex=0;markerIndex<markers.length;markerIndex++){
    const vector=markers[markerIndex].displacement_m;
    const position=markers[markerIndex].point_m.map((value,axis)=>value+factor*vector[axis]);
    const point=projection.project(position),axis=simulation.summary.load_axis||'x';
    const direction=markers[markerIndex].direction || [0,1,2].map(index=>index==='xyz'.indexOf(axis)?Math.sign(simulation.summary.load_N):0);
    const shifted=position.map((value,index)=>value+span*0.1*direction[index]);
    const reference=projection.project(shifted),length=Math.hypot(reference[0]-point[0],reference[1]-point[1])||1;
    const unit=[(reference[0]-point[0])/length,(reference[1]-point[1])/length],start=[point[0]-unit[0]*55*pixel,point[1]-unit[1]*55*pixel];
    context.strokeStyle=themeDark?'#f1b956':'#a56608';context.fillStyle=context.strokeStyle;context.lineWidth=2*pixel;
    context.beginPath();context.moveTo(...start);context.lineTo(point[0],point[1]);context.stroke();context.beginPath();context.moveTo(point[0],point[1]);
    context.lineTo(point[0]-unit[0]*10*pixel-unit[1]*5*pixel,point[1]-unit[1]*10*pixel+unit[0]*5*pixel);context.lineTo(point[0]-unit[0]*10*pixel+unit[1]*5*pixel,point[1]-unit[1]*10*pixel-unit[0]*5*pixel);context.closePath();context.fill();
    if(markerIndex===0)context.fillText(`${simulation.summary.load_kind==='traction'?'Total ':''}${simulation.summary.load_N} N · ${axis.startsWith('normal-')?'surface normal':axis.toUpperCase()}`,start[0]-15*pixel,start[1]-10*pixel);
    }
  }
}
// ---- Animated GIF export of a mode shape -------------------------------------------------
// One vibration cycle is rendered frame by frame from this viewport, quantized to a shared
// 256-colour median-cut palette and written as a looping GIF89a with standard LZW coding.
const gifExportState=window.gifExportState={status:'idle',progress:0,frames:0,data:null,error:null,bytes:0,width:0,height:0};
const GIF_BACKGROUND={light:'#eef3f8',dark:'#16243a',midnight:'#080c14',page:'#152330'};
function gifBackground(){return document.body.classList.contains('desktop')?(document.body.classList.contains('midnight')?GIF_BACKGROUND.midnight:themeDark?GIF_BACKGROUND.dark:GIF_BACKGROUND.light):GIF_BACKGROUND.page;}
function captureGifFrame(phase,output,outputContext){
  phaseOverride=phase;renderFrame();
  outputContext.fillStyle=gifBackground();outputContext.fillRect(0,0,output.width,output.height);
  if(gpuRenderer)outputContext.drawImage(meshCanvas,0,0,output.width,output.height);
  outputContext.drawImage(canvas,0,0,output.width,output.height);
  return outputContext.getImageData(0,0,output.width,output.height).data;
}
function medianCutPalette(samples,maximum=256){
  const histogram=new Uint32Array(32768);
  for(const pixels of samples)for(let index=0;index<pixels.length;index+=4)histogram[((pixels[index]>>3)<<10)|((pixels[index+1]>>3)<<5)|(pixels[index+2]>>3)]++;
  const bins=[];for(let bin=0;bin<32768;bin++)if(histogram[bin])bins.push(bin);
  const channel=(bin,c)=>c===0?bin>>10:c===1?(bin>>5)&31:bin&31;
  function describe(list){
    let low=[31,31,31],high=[0,0,0],count=0;
    for(const bin of list){count+=histogram[bin];for(let c=0;c<3;c++){const v=channel(bin,c);if(v<low[c])low[c]=v;if(v>high[c])high[c]=v;}}
    const ranges=high.map((v,c)=>v-low[c]),axis=ranges.indexOf(Math.max(...ranges));
    return {list,count,axis,score:ranges[axis]*Math.sqrt(count)};
  }
  const boxes=[describe(bins)];
  while(boxes.length<maximum){
    let best=-1,bestScore=0;for(let index=0;index<boxes.length;index++)if(boxes[index].list.length>1&&boxes[index].score>bestScore){best=index;bestScore=boxes[index].score;}
    if(best<0)break;
    const box=boxes[best];box.list.sort((left,right)=>channel(left,box.axis)-channel(right,box.axis));
    let running=0,split=1;for(let index=0;index<box.list.length-1;index++){running+=histogram[box.list[index]];if(running>=box.count/2){split=index+1;break;}split=index+1;}
    boxes.splice(best,1,describe(box.list.slice(0,split)),describe(box.list.slice(split)));
  }
  const palette=new Uint8Array(768);
  boxes.forEach((box,index)=>{
    const sum=[0,0,0];let count=0;
    for(const bin of box.list){const weight=histogram[bin];count+=weight;for(let c=0;c<3;c++)sum[c]+=(channel(bin,c)*8+4)*weight;}
    for(let c=0;c<3;c++)palette[index*3+c]=Math.min(255,Math.round(sum[c]/Math.max(count,1)));
  });
  return {palette,size:Math.max(boxes.length,2)};
}
function indexPixels(pixels,palette,size,lookup){
  const indices=new Uint8Array(pixels.length/4);
  for(let pixel=0,index=0;index<pixels.length;index+=4,pixel++){
    const bin=((pixels[index]>>3)<<10)|((pixels[index+1]>>3)<<5)|(pixels[index+2]>>3);
    let entry=lookup[bin];
    if(entry<0){
      let bestDistance=Infinity;const r=(bin>>10)*8+4,g=((bin>>5)&31)*8+4,b=(bin&31)*8+4;
      for(let candidate=0;candidate<size;candidate++){const dr=palette[candidate*3]-r,dg=palette[candidate*3+1]-g,db=palette[candidate*3+2]-b,distance=dr*dr*2+dg*dg*4+db*db*3;if(distance<bestDistance){bestDistance=distance;entry=candidate;}}
      lookup[bin]=entry;
    }
    indices[pixel]=entry;
  }
  return indices;
}
function lzwEncode(indices,minimumCodeSize,output){
  const clearCode=1<<minimumCodeSize,endCode=clearCode+1;
  let codeSize=minimumCodeSize+1,nextCode=endCode+1,table=new Map(),bitBuffer=0,bitCount=0;
  const block=[];
  function flushBlock(force){while(block.length>=255||(force&&block.length)){const chunk=block.splice(0,255);output.push(chunk.length,...chunk);}}
  function emit(code){bitBuffer|=code<<bitCount;bitCount+=codeSize;while(bitCount>=8){block.push(bitBuffer&255);bitBuffer>>>=8;bitCount-=8;}if(block.length>=255)flushBlock(false);}
  output.push(minimumCodeSize);
  emit(clearCode);
  let current=indices[0];
  for(let position=1;position<indices.length;position++){
    const symbol=indices[position],key=(current<<8)|symbol,known=table.get(key);
    if(known!==undefined){current=known;continue;}
    emit(current);
    if(nextCode===4096){emit(clearCode);table=new Map();nextCode=endCode+1;codeSize=minimumCodeSize+1;}
    else{if(nextCode>=(1<<codeSize))codeSize++;table.set(key,nextCode++);}
    current=symbol;
  }
  emit(current);emit(endCode);
  if(bitCount>0){block.push(bitBuffer&255);bitBuffer=0;bitCount=0;}
  flushBlock(true);output.push(0);
}
function gifBytes(width,height,palette,frames,delay){
  const bytes=[...'GIF89a'].map(character=>character.charCodeAt(0));
  const word=value=>[value&255,(value>>8)&255];
  bytes.push(...word(width),...word(height),0xF7,0,0,...palette);
  bytes.push(0x21,0xFF,11,...[...'NETSCAPE2.0'].map(character=>character.charCodeAt(0)),3,1,0,0,0);
  for(const indices of frames){
    bytes.push(0x21,0xF9,4,0x04,...word(delay),0,0);
    bytes.push(0x2C,0,0,0,0,...word(width),...word(height),0);
    const encoded=[];lzwEncode(indices,8,encoded);for(const value of encoded)bytes.push(value);
  }
  bytes.push(0x3B);
  return new Uint8Array(bytes);
}
function toBase64(bytes){let text='';for(let index=0;index<bytes.length;index+=0x8000)text+=String.fromCharCode.apply(null,bytes.subarray(index,index+0x8000));return btoa(text);}
function startModeGifExport(options={}){
  if(!isModal)return Promise.reject(new Error('GIF export is available for modal results only'));
  if(gifExportState.status==='running')return Promise.reject(new Error('A GIF export is already running'));
  const frameCount=Math.max(8,Math.min(96,Math.round(options.frames||36)));
  const delay=Math.max(2,Math.round(options.delay||100/frameCount));
  const scale=options.width?Math.min(1,options.width/canvas.width):1;
  const output=document.createElement('canvas');
  output.width=Math.max(16,Math.round(canvas.width*scale));output.height=Math.max(16,Math.round(canvas.height*scale));
  const outputContext=output.getContext('2d',{willReadFrequently:true});
  const restore={animation:modeAnimation};
  Object.assign(gifExportState,{status:'running',progress:0,frames:frameCount,data:null,error:null,bytes:0,width:output.width,height:output.height});
  modeAnimation=false;exportingGif=true;
  const phases=Array.from({length:frameCount},(_,index)=>Math.cos(2*Math.PI*index/frameCount));
  const finish=()=>{phaseOverride=null;exportingGif=false;modeAnimation=restore.animation;draw();};
  return new Promise((resolve,reject)=>{
    let palette,size,lookup;const frames=[];let index=0;
    function step(){
      try{
        if(!palette){
          const samples=[0,Math.floor(frameCount/4),Math.floor(frameCount/2)].map(sample=>captureGifFrame(phases[sample],output,outputContext));
          ({palette,size}=medianCutPalette(samples));lookup=new Int16Array(32768).fill(-1);
        }
        const deadline=performance.now()+30;
        while(index<frameCount&&performance.now()<deadline){frames.push(indexPixels(captureGifFrame(phases[index],output,outputContext),palette,size,lookup));index++;}
        gifExportState.progress=index/frameCount*0.9;
        if(index<frameCount){setTimeout(step,0);return;}
        const bytes=gifBytes(output.width,output.height,palette,frames,delay);
        Object.assign(gifExportState,{status:'done',progress:1,data:toBase64(bytes),bytes:bytes.length});
        finish();resolve(bytes);
      }catch(error){Object.assign(gifExportState,{status:'error',error:String(error&&error.message||error)});finish();reject(error);}
    }
    setTimeout(step,0);
  });
}
function takeGifExport(){const data=gifExportState.data;gifExportState.data=null;gifExportState.status='idle';return data;}
function renderFrame(){
  const started=performance.now();
  modePhase=phaseOverride!==null?phaseOverride:modeAnimation?Math.cos(started*2*Math.PI/1000):1;
  const width=Math.max(1,Math.round(canvas.clientWidth*devicePixelRatio)),height=Math.max(1,Math.round(canvas.clientHeight*devicePixelRatio));
  if(canvas.width!==width || canvas.height!==height){canvas.width=meshCanvas.width=width;canvas.height=meshCanvas.height=height;fitRequested=true;}
  if(deformationDirty)updateDeformation();
  context.clearRect(0,0,width,height);projection=cameraProjection();
  if(gpuRenderer)gpuRenderer.draw(projection.matrix);else drawFallback();
  drawOverlay();viewportStats.frames++;viewportStats.lastFrameMs=performance.now()-started;
  viewportStats.modeAnimation=modeAnimation;viewportStats.modePhase=modePhase;
  if(modeAnimation)draw();
}
slider.oninput=()=>{deformationOverride=null;deformationDirty=true;fitRequested=true;document.getElementById('factor').value=slider.value+'×';draw();};
canvas.oncontextmenu=event=>event.preventDefault();
canvas.onpointerdown=event=>{drag={horizontal:event.clientX,vertical:event.clientY,startX:event.clientX,startY:event.clientY,moved:false,button:event.button,pan:event.shiftKey||event.button===1||event.button===2};canvas.setPointerCapture(event.pointerId);event.preventDefault();};
canvas.onpointermove=event=>{
  if(!drag)return;
  const horizontal=event.clientX-drag.horizontal,vertical=event.clientY-drag.vertical;
  if(Math.hypot(event.clientX-drag.startX,event.clientY-drag.startY)>4)drag.moved=true;
  if(drag.pan){panX+=horizontal*devicePixelRatio;panY+=vertical*devicePixelRatio;}else{yaw+=horizontal*0.008;pitch-=vertical*0.008;}
  drag.horizontal=event.clientX;drag.vertical=event.clientY;draw();
};
canvas.onpointerup=event=>{
  if(facePickMode && drag && !drag.moved && drag.button===0 && !drag.pan){
    const rectangle=canvas.getBoundingClientRect();toggleFaceAt((event.clientX-rectangle.left)*devicePixelRatio,(event.clientY-rectangle.top)*devicePixelRatio);
  }
  drag=null;draw();
};
canvas.onpointercancel=()=>{drag=null;draw();};
canvas.addEventListener('wheel',event=>{
  event.preventDefault();
  const previous=cameraZoom;cameraZoom=Math.min(1e12,Math.max(1e-12,cameraZoom*Math.exp(-event.deltaY*0.001)));
  const ratio=cameraZoom/previous,rectangle=canvas.getBoundingClientRect();
  const mouse=[(event.clientX-rectangle.left)*devicePixelRatio,(event.clientY-rectangle.top)*devicePixelRatio];
  const origin=[canvas.width/2-55*devicePixelRatio,canvas.height/2+15*devicePixelRatio];
  panX=mouse[0]-origin[0]-(mouse[0]-origin[0]-panX)*ratio;panY=mouse[1]-origin[1]-(mouse[1]-origin[1]-panY)*ratio;draw();
},{passive:false});
document.getElementById('reset').onclick=resetViewport;
document.getElementById('range').textContent=isThermal?`Temperature: ${scalarRanges[4][0].toPrecision(5)} → ${scalarRanges[4][1].toPrecision(5)} °C`:isModal?'Normalized mode shape: 0 → 1 (dimensionless); amplitude is arbitrary':`0 m → ${maximum.toExponential(5)} m`;
if(isThermal){document.querySelector('h1').textContent='Steady thermal analysis';document.querySelector('main>p').textContent='Temperature and heat flux · SI solver units · Celsius display';slider.parentElement.style.display='none';document.querySelector('main>p:last-child').textContent='Steady conduction only; unassigned surfaces are insulated. No thermal expansion is calculated.';}
if(isModal){
  document.querySelector('main>p').textContent=`Modal analysis · Mode ${simulation.summary.mode_number} · ${simulation.summary.frequency_Hz.toPrecision(6)} Hz · undamped, unprestressed`;
  slider.parentElement.style.display='none';
  document.querySelector('main>p:last-child').textContent='Normalized eigenvector; this is not a forced response or physical displacement amplitude. Animation plays at 1 Hz for inspection.';
  const animationButton=document.createElement('button');animationButton.textContent='Animate mode (1 Hz playback)';
  animationButton.onclick=()=>{setModeAnimation(!modeAnimation);animationButton.textContent=modeAnimation?'Pause mode':'Animate mode (1 Hz playback)';};
  document.getElementById('reset').after(animationButton);
  const gifButton=document.createElement('button');gifButton.textContent='Export GIF';gifButton.style.marginLeft='8px';
  gifButton.onclick=()=>{gifButton.disabled=true;gifButton.textContent='Exporting…';
    startModeGifExport({frames:36,width:960}).then(bytes=>{
      const link=document.createElement('a');link.href=URL.createObjectURL(new Blob([bytes],{type:'image/gif'}));
      link.download=`mode-${simulation.summary.mode_number}-${simulation.summary.frequency_Hz.toPrecision(4)}Hz.gif`;link.click();
      setTimeout(()=>URL.revokeObjectURL(link.href),10000);takeGifExport();
    }).catch(error=>alert(String(error))).finally(()=>{gifButton.disabled=false;gifButton.textContent='Export GIF';});};
  animationButton.after(gifButton);
}
document.getElementById('summary').textContent=JSON.stringify(simulation.summary,null,2);
if(simulation.von_mises_Pa){
  const selection=document.createElement('select');selection.id='resultField';
  for(const [value,label] of (isThermal?[['stress','Temperature (°C)'],['magnitude','Heat flux magnitude (W/m²)'],['x','Heat flux X'],['y','Heat flux Y'],['z','Heat flux Z']]:[['magnitude','Total displacement'],['x','Ux'],['y','Uy'],['z','Uz'],['stress','Recovered von Mises (MPa)']])){
    const option=document.createElement('option');option.value=value;option.textContent=label;selection.append(option);
  }
  selection.onchange=()=>setResultComponent(selection.value);document.getElementById('reset').before(selection);
  document.querySelector('main>p:last-child').textContent='Recovered nodal stress is available. Peaks at ideal fixed edges may be singular; use mesh refinement and physical support assumptions when interpreting stress.';
}
new ResizeObserver(()=>{fitRequested=true;draw();}).observe(canvas);
draw();
