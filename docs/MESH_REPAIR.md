# Automatic surface preparation and repair

For **STL, OBJ and 3MF**, click **Generate mesh** as usual. Repair runs automatically during meshing, static solving and modal solving, including CLI/MCP jobs using the same importer. No extra packages or manual repair button are required. STEP/IGES/BREP continue through the existing exact-CAD path.

The importer works on a temporary copy of the triangle coordinates. It merges coincident vertices using the existing tiny, model-relative tolerance, drops degenerate triangles, removes duplicate facets and propagates a consistent orientation across neighboring triangles. A wholly inside-out shell is reversed. It then checks for a connected, closed shell and nonzero enclosed volume. The original imported file is never rewritten.

## The “Wrong topology of boundary mesh for parametrization” error

This message occurs during Gmsh's construction of parametrized face patches; it does not by itself establish that a model has holes. A closed triangle surface can have patches that Gmsh cannot parameterize.

After the initial 40° face classification fails, the importer discards the partially constructed Gmsh model and retries the same cleaned surface at 25°, then 10°, also allowing sharper curve splits. This follows Gmsh's [discrete-surface classification and parametrization workflow](https://gmsh.info/doc/texinfo/#t13). There are at most three construction attempts. Exhausting them produces an actionable error recommending STEP export from the original CAD or external mesh repair.

These retries recover some patch-construction failures, not every possible topology error. The particular source file in the user's screenshot was not available in the current workspace's job history, so recovery of that exact model has not been verified.

## Seeing what happened

Completed jobs include an **Automatic surface preparation** line in **Messages / Solver Jobs**. It reports duplicate/degenerate removals, reorientation, and whether smaller face patches were required. Static and modal summaries include the same `mesh_repair` record.

Each surface-mesh import writes **`mesh.repair.json`** beside **`mesh.msh`** in the job's output directory. This includes counts, weld tolerance in meters, input enclosed volume, patch angles attempted, construction failures and final status. A failed preparation also writes the available diagnostic report. Open the job directory through **File locations** to inspect it. Convergence runs keep a separate report in each mesh-level directory.

Smaller patches can change pickable face IDs. After a repair/re-import, inspect the mesh and review selected support/load faces before trusting a solve.

## Limits and checks

Automatic preparation does not fill holes, bridge gaps, join separate shells, smooth/decimate the model, reconstruct missing geometry or resolve self-intersections. Non-manifold edges, inconsistent non-orientable topology and multiple shells remain errors. This is not a general mesh-repair or geometric-validity certification tool.

Tests cover duplicate/flipped/degenerate facets, original-file hashes, corrected closed-shell orientation, unchanged box bounds and volume, holes/non-manifold/disconnected surfaces, successful retry after an injected parametrization failure, and bounded failure/reporting. Existing STL/OBJ/3MF versus STEP meshing comparisons remain in place. A CalculiX integration test compares both pristine and automatically repaired STL cantilevers with an exact STEP solve, checking displacement and force balance.
