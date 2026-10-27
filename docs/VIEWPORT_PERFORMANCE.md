# Viewport rendering and top-bar update

The viewport now batches surface triangles into one WebGL indexed draw call, with a second call for mesh edges. Mesh coordinates, displacement components and connectivity are uploaded once per loaded view. Camera motion updates a projection matrix and overlay annotations; it does not sort or rebuild the surface.

Redraw requests are coalesced through `requestAnimationFrame`. Backing canvases resize only when their dimensions change. Scalar ranges are cached; deformation bounds update only when deformation or view mode changes. Rotation retains camera scale; Shift-drag, middle-drag or right-drag pans, the wheel zooms around the pointer, and Fit view recenters the current orientation.

A Canvas 2D fallback remains available when WebGL or required index support is unavailable. It preserves all surface triangles, caches scalar colors, coalesces events and omits mesh-edge strokes during dragging. Its performance is not claimed to match WebGL. A `canvas2d=1` URL query forces this path for testing. A WebGL context-loss event switches to the fallback; context restoration rebuilds GPU resources.

## Measured comparison

Controlled Microsoft Edge headless benchmark, 1200 × 800 viewport, same 19,448-triangle cantilever, 59 measured frame intervals after warm-up:

| Metric | Previous Canvas renderer | New WebGL renderer |
|---|---:|---:|
| Mean frame interval | 87.57 ms | 6.94 ms |
| Approximate frame rate | 11.4 FPS | 144.0 FPS |
| 95th-percentile frame interval | 104.2 ms | 7.1 ms |
| Mean JavaScript rendering work | 43.28 ms | 0.17 ms |

The frame-rate improvement in this controlled browser test is approximately 12.6×. JavaScript rendering work measures CPU command submission, not GPU completion. These numbers are not a guaranteed native-window frame rate; display refresh, browser scheduling, driver and device affect the result. The running Qt desktop was also visually checked and reported the WebGL rendering path.

Interaction checks passed for both WebGL and the forced Canvas fallback: rotation, true camera panning, wheel zoom, fit/reset, theme and displacement-component selection. One hundred synchronous redraw requests produced one rendered frame. Camera and appearance changes did not re-upload mesh data. All triangles were retained; scientific displacement arrays were unchanged.

## Existing saved results

The desktop extracts the saved numerical JSON and generates an up-to-date viewer in the ignored workspace `.viewer-cache` directory. Cache identity includes the saved file and renderer modification times. Legacy viewer JavaScript is never executed during this conversion. Original result HTML, solver files and numerical fields remain unchanged. Cached views are published atomically.

The **DOO DOO DYNAMICS / SIMULATOR** title and theme control now occupy the full-width top application/menu strip. The separate banner above the viewport was removed, recovering vertical space for the model. Native window controls and menus remain available.

References: [WebGL batching guidance](https://developer.mozilla.org/en-US/docs/Web/API/WebGL_API/WebGL_best_practices), [display-synchronized animation](https://developer.mozilla.org/en-US/docs/Web/API/Window/requestAnimationFrame), [Qt main-window menu widgets](https://doc.qt.io/qt-6/qmainwindow.html#setMenuWidget).
