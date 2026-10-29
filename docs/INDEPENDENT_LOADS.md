# Independent forces and pressures

Select a static or convergence study, apply any edited material/mesh inputs, then choose **Independent forces / pressures…** in the left properties panel.

Use **Add force** for a total surface-force vector in **N**, with independent X, Y and Z components. Use **Add pressure** for a uniform normal pressure in **Pa**. Positive pressure pushes inward on each selected surface; negative pressure pulls outward. Each entry has its own name, enabled flag, selected faces and fallback bounding face. The entries act simultaneously in the same linear solve; they are not separate load steps.

Select an entry and choose **Pick faces for this load**. The editor hides while you select model faces. Use **Save picked faces** in the main window to return the selection to that entry. You can also type comma-separated CAD face IDs. With no region selected, that entry uses its own fallback face. Switching entries retains their individual components and regions.

**Apply loads** saves the list. **Apply and preview** also builds a mesh and displays arrows from the same surface integration used in the solver. Distinct colors identify loads. Force arrows follow the full vector; pressure arrows follow local normals. A dot/cross in a circle denotes motion toward/away from the camera when a vector is nearly perpendicular to the screen. Arrow lengths are illustrative, not a scale drawing of force magnitude; labels give the actual N or Pa. The preview samples surface triangles rather than drawing an arrow at every integration point.

A nonempty list replaces the legacy single load; hidden legacy values are not added to it. Remove every entry and apply to restore the original face/point/traction setup. New independent entries currently support distributed surface forces and pressures, not arbitrary point forces or time-dependent loading. Modal studies ignore this list and do not include prestress. Thermal boundaries remain separate. Importing replacement geometry clears face selections and the independent list.

All entries are assembled into one consistent nodal force vector before solving. Overlapping surfaces superpose. Force and moment balance are checked against the combined distribution, using a nonzero scale even for pure couples with zero net force. Quadratic surface triangles use their midside-node weights, matching the existing straight-sided C3D10 traction integration. Pressure contributes `pressure × actual selected area`, not an incorrectly interpreted total force.

The multiple-load result's **Load-weighted response** is `Σ(u·f) / Σ|f|`, in meters internally; the denominator sums each entry's nodal force magnitudes before combining entries, so canceling force couples retain a nonzero scale. It replaces the ambiguous single-direction loaded-area response in convergence studies. Maximum displacement and stress retain their previous meanings.

MCP `set_analysis_parameters(..., load_cases=[...])` accepts:

```json
[
  {"name":"Pull", "kind":"force", "components_N":[2,3,0], "region":{"faces":[7]}, "surface":"x-max", "enabled":true},
  {"name":"Top pressure", "kind":"pressure", "pressure_Pa":1000, "region":{"faces":[12]}, "surface":"z-max", "enabled":true}
]
```

Use valid IDs from the actual imported model. An empty list restores the legacy load. Up to 32 entries are supported. Automated checks verify independent surfaces, direction, pressure-area integration, preview vectors, linear superposition and global force/moment equilibrium.
