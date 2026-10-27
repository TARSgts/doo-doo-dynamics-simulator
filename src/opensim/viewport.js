if(new URLSearchParams(location.search).has('desktop')) document.body.classList.add('desktop');
const canvas = document.getElementById('view');
const meshCanvas = document.getElementById('mesh');
const context = canvas.getContext('2d');
const slider = document.getElementById('scale');
const nodeCount = simulation.points.length;
const faceCount = simulation.faces.length;
const isModal = simulation.summary.analysis === 'modal';
let modeAnimation = false, modePhase = 1;
let catMode = false;
const coordinates = new Float64Array(nodeCount * 3);
const deformation = new Float64Array(nodeCount * 3);
const deformed = new Float64Array(nodeCount * 3);
const magnitudes = new Float64Array(nodeCount);
const scalarRanges = [[0,0],[Infinity,-Infinity],[Infinity,-Infinity],[Infinity,-Infinity]];
const bounds = [[Infinity,-Infinity],[Infinity,-Infinity],[Infinity,-Infinity]];
for(let node=0;node<nodeCount;node++){
  magnitudes[node] = Math.hypot(...simulation.displacement[node]);
  scalarRanges[0][1] = Math.max(scalarRanges[0][1],magnitudes[node]);
  for(let axis=0;axis<3;axis++){
    coordinates[node*3+axis] = simulation.points[node][axis];
    deformation[node*3+axis] = simulation.displacement[node][axis];
    bounds[axis][0] = Math.min(bounds[axis][0],coordinates[node*3+axis]);
    bounds[axis][1] = Math.max(bounds[axis][1],coordinates[node*3+axis]);
    scalarRanges[axis+1][0] = Math.min(scalarRanges[axis+1][0],deformation[node*3+axis]);
    scalarRanges[axis+1][1] = Math.max(scalarRanges[axis+1][1],deformation[node*3+axis]);
  }
}
const maximum = scalarRanges[0][1];
const center = bounds.map(bound=>(bound[0]+bound[1])/2);
const span = Math.max(...bounds.map(bound=>bound[1]-bound[0]));
const faceIndices = new Uint32Array(simulation.faces.flat());
const scalarBuffer = new Float32Array(nodeCount*4);
for(let node=0;node<nodeCount;node++){
  scalarBuffer.set([magnitudes[node],...simulation.displacement[node]],node*4);
}
let yaw=-0.45, pitch=0.5, drag=null;
let viewportMode=simulation.summary.view==='mesh'?'mesh':'results';
let edgeVisibility=true, themeDark=!document.body.classList.contains('desktop');
let deformationOverride=isModal && maximum ? span*0.1/maximum : null, resultComponent='magnitude';
let framePending=false, deformationDirty=true, fitRequested=true, colorDirty=true;
let factor=0, cameraZoom=1, panX=0, panY=0, depthScale=1;
let target=center.slice(), deformedBounds=bounds.map(bound=>bound.slice());
let projection=null, fallbackColors=[], fallbackDepth=new Float64Array(faceCount);
const fallbackOrder=Array.from({length:faceCount},(_,index)=>index);
const projected=new Float64Array(nodeCount*3);
const viewportStats=window.viewportStats={renderer:'canvas2d',frames:0,drawRequests:0,lastFrameMs:0,geometryUploads:0};

function createGpuRenderer(){
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
      attribute vec3 position;attribute vec3 displacement;attribute vec4 values;
      uniform mat4 projection;uniform vec3 target;uniform float deformationScale;uniform vec4 component;
      varying float scalar;
      void main(){gl_Position=projection*vec4(position+deformationScale*displacement-target,1.0);scalar=dot(values,component);}
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
    const IndexType=wideIndices?Uint32Array:Uint16Array;
    function indexBuffer(data){const buffer=gpu.createBuffer();gpu.bindBuffer(gpu.ELEMENT_ARRAY_BUFFER,buffer);gpu.bufferData(gpu.ELEMENT_ARRAY_BUFFER,new IndexType(data),gpu.STATIC_DRAW);return buffer;}
    const triangles=indexBuffer(faceIndices);
    const lineIndices=new IndexType(faceCount*6);
    for(let face=0;face<faceCount;face++){
      const first=faceIndices[face*3],second=faceIndices[face*3+1],third=faceIndices[face*3+2];
      lineIndices.set([first,second,second,third,third,first],face*6);
    }
    const lines=indexBuffer(lineIndices);
    const uniforms=Object.fromEntries(['projection','target','deformationScale','component','range','results','edges','edgeColor','solidColor'].map(name=>[name,gpu.getUniformLocation(program,name)]));
    gpu.enable(gpu.DEPTH_TEST);gpu.depthFunc(gpu.LEQUAL);gpu.clearColor(0,0,0,0);
    viewportStats.geometryUploads++;
    return {draw(matrix){
      gpu.viewport(0,0,meshCanvas.width,meshCanvas.height);gpu.clear(gpu.COLOR_BUFFER_BIT|gpu.DEPTH_BUFFER_BIT);
      gpu.useProgram(program);gpu.uniformMatrix4fv(uniforms.projection,false,matrix);
      gpu.uniform3fv(uniforms.target,target.map((value,axis)=>value-center[axis]));
      gpu.uniform1f(uniforms.deformationScale,factor*modePhase);
      const component=[0,0,0,0];component[componentIndex()]=1;gpu.uniform4fv(uniforms.component,component);
      gpu.uniform2fv(uniforms.range,scalarRanges[componentIndex()]);gpu.uniform1i(uniforms.results,viewportMode==='results');
      gpu.uniform3fv(uniforms.solidColor,themeDark?[0.44,0.55,0.68]:[0.68,0.75,0.82]);
      gpu.uniform1i(uniforms.edges,false);gpu.enable(gpu.POLYGON_OFFSET_FILL);gpu.polygonOffset(1,1);
      gpu.bindBuffer(gpu.ELEMENT_ARRAY_BUFFER,triangles);gpu.drawElements(gpu.TRIANGLES,faceCount*3,wideIndices?gpu.UNSIGNED_INT:gpu.UNSIGNED_SHORT,0);
      gpu.disable(gpu.POLYGON_OFFSET_FILL);
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

function componentIndex(){return resultComponent==='magnitude'?0:'xyz'.indexOf(resultComponent)+1;}
function setTheme(theme){themeDark=theme==='dark';document.body.classList.toggle('dark',themeDark);draw();}
function setCatMode(value){catMode=Boolean(value);draw();}
function setResultComponent(component){if(!['magnitude','x','y','z'].includes(component))return;resultComponent=component;colorDirty=true;draw();}
function setViewportMode(mode){if(mode==='modal')mode='results';if(viewportMode!==mode){viewportMode=mode;deformationDirty=true;fitRequested=true;}draw();}
function setModeAnimation(value){modeAnimation=isModal && Boolean(value);if(!modeAnimation)modePhase=1;draw();}
function setEdgeVisibility(value){edgeVisibility=Boolean(value);draw();}
function setDeformationScale(value){deformationOverride=value==='auto'?(maximum?span*0.1/maximum:0):Number(value);deformationDirty=true;fitRequested=true;draw();}
function resetViewport(){panX=panY=0;fitRequested=true;draw();}
function setViewOrientation(orientation){yaw=orientation==='isometric'?-0.45:0;pitch=orientation==='front'?0:orientation==='top'?-Math.PI/2:0.5;panX=panY=0;fitRequested=true;draw();}
function draw(){
  viewportStats.drawRequests++;
  if(framePending)return;
  framePending=true;
  requestAnimationFrame(()=>{framePending=false;renderFrame();});
}
function updateDeformation(){
  factor=viewportMode==='results'?(deformationOverride??Number(slider.value)):0;
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
    return [relative[0]*cosineYaw-relative[1]*sineYaw,depth*sinePitch-relative[2]*cosinePitch,depth*cosinePitch+relative[2]*sinePitch];
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
    horizontalScale*cosineYaw,-verticalScale*sinePitch*sineYaw,-cosinePitch*sineYaw/depthScale,0,
    -horizontalScale*sineYaw,-verticalScale*sinePitch*cosineYaw,-cosinePitch*cosineYaw/depthScale,0,
    0,verticalScale*cosinePitch,-sinePitch/depthScale,0,
    2*offset[0]/canvas.width-1,1-2*offset[1]/canvas.height,0,1
  ]);
  return {matrix,project(point){const rotated=rotate(point[0],point[1],point[2]);return [offset[0]+rotated[0]*cameraZoom,offset[1]+rotated[1]*cameraZoom,rotated[2]];}};
}
function drawFallback(){
  const component=componentIndex(),range=scalarRanges[component];
  if(colorDirty){
    fallbackColors=Array.from({length:faceCount},(_,face)=>{
      let average=0;for(let corner=0;corner<3;corner++)average+=scalarBuffer[faceIndices[face*3+corner]*4+component]/3;
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
    context.fillStyle=viewportMode==='results'?fallbackColors[face]:(themeDark?'#718cae':'#aebed0');context.fill();
    if(edgeVisibility && viewportMode!=='geometry' && !drag)context.stroke();
  }
}
function drawOverlay(){
  const pixel=devicePixelRatio,range=scalarRanges[componentIndex()];
  context.font=`${12*pixel}px Segoe UI`;context.fillStyle=themeDark?'#bbd2ec':'#3a506b';
  context.fillText(`${simulation.summary.element_type||'Tetrahedra'} · ${faceCount.toLocaleString()} ${catMode?'tiny triangle beans':'surface triangles'} · ${gpuRenderer?'WebGL':'Canvas fallback'}`,20*pixel,27*pixel);
  if(viewportMode==='results'){
    context.fillText(isModal?`${catMode?'Wiggle':'Mode'} ${simulation.summary.mode_number} · ${simulation.summary.frequency_Hz.toPrecision(6)} Hz · ${catMode?'purr shape · dance speed':'normalized shape · playback'} 1 Hz`:`${catMode?'Wiggle exaggeration':'Deformation display'}: ${factor.toPrecision(3)}×`,20*pixel,46*pixel);
    const gradient=context.createLinearGradient(0,75*pixel,0,210*pixel);
    for(let stop=0;stop<=6;stop++)gradient.addColorStop(stop/6,`hsl(${225*stop/6} 75% 57%)`);
    context.fillStyle=gradient;context.fillRect(canvas.width-112*pixel,75*pixel,14*pixel,135*pixel);
    const units=isModal?'(norm.)':'(mm)',unitScale=isModal?1:1000;
    context.fillStyle=themeDark?'#c6d7ec':'#34485f';context.fillText((resultComponent==='magnitude'?'|U|':`U${resultComponent}`)+' '+units,canvas.width-125*pixel,58*pixel);
    context.fillText((range[1]*unitScale).toPrecision(4),canvas.width-92*pixel,85*pixel);context.fillText((range[0]*unitScale).toPrecision(4),canvas.width-92*pixel,210*pixel);
  }
  const anchor=projection.project([bounds[0][0],center[1],center[2]]);
  context.fillStyle=themeDark?'#41c8d6':'#087f8c';context.beginPath();context.arc(anchor[0],anchor[1],4*pixel,0,2*Math.PI);context.fill();context.fillText(catMode?'NO ZOOMIES':'FIXED',anchor[0]-15*pixel,anchor[1]+25*pixel);
  if(simulation.summary.load_point_m){
    const vector=simulation.summary.load_point_displacement_m||[0,0,0];
    const position=simulation.summary.load_point_m.map((value,axis)=>value+factor*vector[axis]);
    const point=projection.project(position),direction='xyz'.indexOf(simulation.summary.load_axis||'x');
    const shifted=position.slice();shifted[direction]+=span*0.1*Math.sign(simulation.summary.load_N);
    const reference=projection.project(shifted),length=Math.hypot(reference[0]-point[0],reference[1]-point[1])||1;
    const unit=[(reference[0]-point[0])/length,(reference[1]-point[1])/length],start=[point[0]-unit[0]*55*pixel,point[1]-unit[1]*55*pixel];
    context.strokeStyle=themeDark?'#f1b956':'#a56608';context.fillStyle=context.strokeStyle;context.lineWidth=2*pixel;
    context.beginPath();context.moveTo(...start);context.lineTo(point[0],point[1]);context.stroke();context.beginPath();context.moveTo(point[0],point[1]);
    context.lineTo(point[0]-unit[0]*10*pixel-unit[1]*5*pixel,point[1]-unit[1]*10*pixel+unit[0]*5*pixel);context.lineTo(point[0]-unit[0]*10*pixel+unit[1]*5*pixel,point[1]-unit[1]*10*pixel-unit[0]*5*pixel);context.closePath();context.fill();
    context.fillText(`${simulation.summary.load_N} N · ${(simulation.summary.load_axis||'x').toUpperCase()}`,start[0]-15*pixel,start[1]-10*pixel);
  }
}
function renderFrame(){
  const started=performance.now();
  modePhase=modeAnimation?Math.cos(started*2*Math.PI/1000):1;
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
canvas.onpointerdown=event=>{drag={horizontal:event.clientX,vertical:event.clientY,pan:event.shiftKey||event.button===1||event.button===2};canvas.setPointerCapture(event.pointerId);event.preventDefault();};
canvas.onpointermove=event=>{
  if(!drag)return;
  const horizontal=event.clientX-drag.horizontal,vertical=event.clientY-drag.vertical;
  if(drag.pan){panX+=horizontal*devicePixelRatio;panY+=vertical*devicePixelRatio;}else{yaw+=horizontal*0.008;pitch+=vertical*0.008;}
  drag.horizontal=event.clientX;drag.vertical=event.clientY;draw();
};
canvas.onpointerup=canvas.onpointercancel=()=>{drag=null;draw();};
canvas.addEventListener('wheel',event=>{
  event.preventDefault();
  const previous=cameraZoom;cameraZoom=Math.min(1e12,Math.max(1e-12,cameraZoom*Math.exp(-event.deltaY*0.001)));
  const ratio=cameraZoom/previous,rectangle=canvas.getBoundingClientRect();
  const mouse=[(event.clientX-rectangle.left)*devicePixelRatio,(event.clientY-rectangle.top)*devicePixelRatio];
  const origin=[canvas.width/2-55*devicePixelRatio,canvas.height/2+15*devicePixelRatio];
  panX=mouse[0]-origin[0]-(mouse[0]-origin[0]-panX)*ratio;panY=mouse[1]-origin[1]-(mouse[1]-origin[1]-panY)*ratio;draw();
},{passive:false});
document.getElementById('reset').onclick=resetViewport;
document.getElementById('range').textContent=isModal?'Normalized mode shape: 0 → 1 (dimensionless); amplitude is arbitrary':`0 m → ${maximum.toExponential(5)} m`;
if(isModal){
  document.querySelector('main>p').textContent=`Modal analysis · Mode ${simulation.summary.mode_number} · ${simulation.summary.frequency_Hz.toPrecision(6)} Hz · undamped, unprestressed`;
  slider.parentElement.style.display='none';
  document.querySelector('main>p:last-child').textContent='Normalized eigenvector; this is not a forced response or physical displacement amplitude. Animation plays at 1 Hz for inspection.';
  const animationButton=document.createElement('button');animationButton.textContent='Animate mode (1 Hz playback)';
  animationButton.onclick=()=>{setModeAnimation(!modeAnimation);animationButton.textContent=modeAnimation?'Pause mode':'Animate mode (1 Hz playback)';};
  document.getElementById('reset').after(animationButton);
}
document.getElementById('summary').textContent=JSON.stringify(simulation.summary,null,2);
new ResizeObserver(()=>{fitRequested=true;draw();}).observe(canvas);
draw();
