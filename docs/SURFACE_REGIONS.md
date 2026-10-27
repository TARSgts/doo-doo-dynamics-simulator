# Surface regions and recovered stress

The properties panel now includes **Support / load regions…**. Generate a mesh first, then open this dialog to see CAD face IDs with their meshed areas and center coordinates. The dialog accepts comma-separated face IDs for a fully fixed support and for uniform global-vector traction. Empty selections preserve the original X-min support and bounding-plane load behavior.

The optional box uses `xmin,ymin,zmin,xmax,ymax,zmax`, entered in **millimeters** in the desktop and stored as `box_m` in **meters**. A triangle is selected when its corner centroid lies in the box. All its nodes participate, so the patch boundary is mesh-based rather than an exact CAD cut and can extend past the box. Multiple face IDs are combined; a box filters their combined triangles. With no face IDs, the box filters all boundary triangles. Empty, unknown-ID, nonfinite or degenerate support selections are rejected.

A selected support fixes all three translations. It is an approximation of a restrained patch, not a bearing/contact model. It does not provide normal-only contact, sliding, friction, hinge motion or automatic physical support interpretation. Load patches apply one constant vector in global X/Y/Z, normalized to the entered total force. Curved CAD faces are represented by straight-sided surface triangles. Pressure/follower loads remain unavailable.

CAD face IDs belong to the imported topology. New CAD imports and generated examples clear old regions; reselect them after changing geometry. Editing a region invalidates current results and retains previous jobs. Modal analysis uses the same selected fixed-support region and ignores static load regions.

## CLI and MCP

The CLI accepts `--regions regions.json`. For example:

```json
{
  "support_region": {"faces": [1]},
  "load_region": {"faces": [2], "box_m": [0, 0, 0, 1, 0.1, 0.1]}
}
```

The numeric IDs above are illustrative; use the IDs listed for your own CAD. Call `solve` with `--load-kind traction` and the usual signed total force and direction. The MCP `set_analysis_parameters` tool accepts optional `support_region` and `load_region` dictionaries with this schema. Passing `{}` clears a region; omitting an optional dictionary preserves it. Existing MCP clients must reconnect for the expanded tool schema. The catalog still contains 16 tools.

## Stress results

New static solves read the full recovered nodal tensor from CalculiX FRD, preserving `SXX,SYY,SZZ,SXY,SYZ,SZX`. They calculate von Mises stress from that tensor. The desktop result selector and **Solution → Stress contours** show the scalar in **MPa**. The standalone viewer also has a result selector; WebGL and Canvas fallback use the same scalar field.

`fields.npz` retains SI tensor components, equivalent stress, displacement, applied nodal forces and support-node IDs. New VTK exports include a `von_mises_Pa` scalar. These are recovered/averaged nodal quantities, not raw integration-point maxima. Peaks at ideal fixed edges or abrupt load boundaries can be singular; use suitable support physics and stress convergence rather than interpreting the largest displayed value as a material failure prediction. No safety factor or allowable load is calculated automatically.

For geometries without a useful planar X-max tip, the application can report the area-averaged loaded-surface displacement. A custom load region uses this quantity in the result card. The fixed marker is placed at the actual support-node centroid. The **Front XZ · flipped** camera helps view parts whose CAD orientation is upside down relative to service.

## Native solver units

Region-based solves use an equivalent N–mm–MPa native deck to improve numeric scaling for small CAD features. Coordinates are multiplied by 1,000 and elastic modulus divided by 1,000,000. Static displacements and stresses are converted back to SI for app summaries, HTML, VTK and NPZ. Modal native density is divided by the fourth power of the length scale so frequencies remain in Hz. Manifests record the native length/stress/density conversion factors. Raw DAT/FRD files retain native solver units; inspect their manifest before reading them directly.

The solver's element-error checks remain enabled. Nonpositive Jacobians and timeouts fail the job, retaining logs. Unit conversion does not establish mesh quality or justify accepting a failed solve.

## Verification

Tests cover region validation and empty selection, CAD face cataloguing, matching full-face traction to the bounding-plane method, selected supports, clearing obsolete IDs on CAD replacement, uniaxial solid stress, hydrostatic and pure-shear von Mises invariants, strict FRD parsing, static SI/native-unit equivalence, and modal frequency invariance under equivalent native units. Property-layout checks cover three widths and English/Cat modes. The new region/stress functionality passed the 128-test suite before final export and display refinements; targeted checks were repeated afterward.
