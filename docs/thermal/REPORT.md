# Steady thermal verification

Independent Gmsh meshes and CalculiX conduction solves on a 100 × 20 × 20 mm bar, k=10 W/(m·K). Other faces are insulated.

Two-temperature case: X-min=20 °C and X-max=100 °C. Fourier conduction gives T(x)=293.15+800x K, qx=-8000 W/m², heat rate 3.2 W.

Power case: X-min=20 °C, total heat input 0.4 W on X-max. T(x)=293.15+100x K, hot end=30 °C, qx=-1000 W/m².

| Element | Mesh mm | Boundary | Elements | Max T error K | Max flux error % | Relative energy residual |
|---|---:|---|---:|---:|---:|---:|
| C3D4 | 15 | temperature | 187 | 4.29e-05 | 8.22e-13 | 0 |
| C3D4 | 15 | power | 187 | 4.52e-05 | 1.04e-11 | 2.5e-08 |
| C3D4 | 10 | temperature | 254 | 4.68e-05 | 1.02e-12 | 0 |
| C3D4 | 10 | power | 254 | 4.83e-05 | 6.32e-12 | 2.5e-08 |
| C3D10 | 15 | temperature | 187 | 4.89e-05 | 0.001 | 5.83e-15 |
| C3D10 | 15 | power | 187 | 4.92e-05 | 0.001 | 3e-08 |
| C3D10 | 10 | temperature | 254 | 4.85e-05 | 0.001 | 2.78e-15 |
| C3D10 | 10 | power | 254 | 4.94e-05 | 0.001 | 1.5e-08 |

PASS: every nodal temperature is within 0.001 K, recovered heat-flux vectors within 0.01%, and energy residual below 1e-6. Raw values: [validation.csv](validation.csv). These exact linear fields test conductivity, temperature DOF, heat-input integration, mesh order, output parsing and energy balance. They do not establish accuracy for curved boundaries, singular corners or arbitrary meshes.

Additional automated cases check selected CAD faces, mm-to-m scaling, zero and negative heat input, invalid inputs and overlapping thermal boundaries. No convection, radiation, transient heating or thermal expansion is implemented.
