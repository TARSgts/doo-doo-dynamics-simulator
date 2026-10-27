# Perpendicular surface forces

In the desktop **Force direction** dropdown, choose **Perpendicular · inward** to push into the solid, or **Perpendicular · outward** to pull away from it. Choosing either automatically selects **Uniform surface traction**. Pick force faces on the model or use a bounding-plane surface, enter a positive **Total force (N)** and Solve. A negative force reverses the chosen direction. Point and legacy equal-node loading remain available with X/Y/Z directions.

The input remains newtons, not pressure. For a flat face, the entered magnitude equals the resultant force magnitude. For curved or multiple faces, the same pressure magnitude acts over every selected triangle, with direction following its local meshed surface normal. The entered magnitude is the **sum of local force magnitudes**; the net vector can be smaller or zero. For example, equal inward loading around a closed surface has no net force, though it still stresses the material. The dropdown tooltip and an explanatory note describe this distinction.

## Meaning and implementation

Let A be the total selected mesh area and n the unit outward normal of each surface triangle. With signed force F:

- `normal-in`: t = -(F/A)n.
- `normal-out`: t = +(F/A)n.
- X/Y/Z: the existing constant global-vector traction remains unchanged.

The material side is identified from the opposite node of the adjacent tetrahedron. Normals do not depend on CAD triangle winding or the position of a global model center, so an inward load on an inside hole wall pushes into the surrounding material. A surface record without exactly one adjacent solid is rejected.

For each linear triangle, the integrated vector is shared equally among the three corner nodes. For a straight-sided six-node quadratic triangle, corner integrals are zero and midside integrals each equal one third of the triangle force. Every resulting X/Y/Z component is exported to CalculiX. Force and moment equilibrium use the complete vectors, including applied forces at constrained nodes.

This is a linear static, initial-geometry load. Normals are those of flat mesh triangles: they approximate curved CAD surfaces and need mesh refinement. Non-affine quadratic surface triangles are rejected. It does not add follower pressure, changing contact, fluid pressure fields or a pressure-in-Pa input field. The fully fixed support approximation is unchanged.

## Results and automation

Arrows follow their individual local force directions. Summaries retain the net `applied_force_N` vector, reactions and equilibrium residuals. Normal loads also report:

- `normal_pressure_Pa`: positive for inward compression, negative for outward tension, including force-sign reversal.
- `traction_magnitude_Pa`: absolute F/A.
- `loaded_surface_mean_normal_displacement_m`: area-weighted displacement projected along each local applied-force direction, including sign reversal.
- `load_force_meaning`: explains the scalar-sum versus net-vector distinction.

`uniform_traction_Pa` remains signed F/A relative to the selected direction convention. The desktop displays mean movement along the local normal-force direction instead of inventing an X/Y/Z component. Its job log shows the full reaction vector.

CLI: use `--load-kind traction --load-axis normal-in` or `normal-out`, with the existing signed `--load`, surface/region and support settings. MCP uses those same strings in `set_analysis_parameters`; no tools were added. API inputs reject normal directions combined with point/equal-node loading. Modal analysis continues to ignore all static loads.

## Verification

Tests compare inward and outward forces on all six box faces for C3D4/C3D10 against equivalent global-axis traction, including force reversal and moments. Closed tetrahedra with reversed face winding verify zero net force/moment and pressure virtual work. An inside cylindrical hole checks material-side orientation. Planar and spatially rotated axial bars are solved in both directions against FL/EA, uniform stress and three-component reactions. Desktop tests cover automatic traction selection, incompatible-option disabling and saved unit meanings. A visible Windows solve verified the dropdown, local arrows, normal-displacement card and vector reaction log.

The complete suite passed **179 tests in 101.02 seconds**. The native inward-loaded bar gave mean normal movement 2.380952e-7 m versus FL/EA = 2.38095238e-7 m, force residual 4.0e-8 and moment residual 5.1e-11.

The rotated-bar tests also exposed an input-format issue: long negative scientific values could exceed CalculiX's real-number read window. Static and modal numeric exports now retain 15 significant digits when they fit, otherwise 12, keeping every numeric field within 20 characters. Regression checks cover tiny and large exponents. CalculiX's own [`cloads.f` input reader](https://github.com/Dhondtguido/CalculiX/blob/master/src/cloads.f) reads the load value from the first 20 characters; no proprietary code is used.
