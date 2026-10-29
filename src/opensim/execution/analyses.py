"""Thin adapters: common job interface, unchanged solver algorithms."""
from opensim.cli import solve


def cfd_validation(cad,directory,parameters,progress):
    from opensim.cfd_validation import run_cfd_validation
    result = run_cfd_validation(directory / 'cfd_validation', progress=progress)

    return result


def cfd(cad,directory,parameters,progress):
    if parameters['cfd_case']=='cad':
        if parameters['cfd_backend']=='su2':
            from opensim.su2_flow import solve_su2
            result=solve_su2(cad,directory/'cfd',parameters,progress=progress)
        else:
            from opensim.cad_flow import solve_cad_flow
            result=solve_cad_flow(cad,directory/'cfd',parameters,progress=progress)
    else:
        from opensim.cfd import run_cfd
        result = run_cfd(directory / 'cfd', parameters, progress=progress)

    return result


def thermal(cad,directory,parameters,progress):
    from opensim.thermal import solve_thermal
    result = solve_thermal(cad, directory / "thermal", size=parameters["mesh_size_m"], scale=parameters["cad_scale"],
                           order=parameters["element_order"], parameters=parameters, progress=progress)

    return result


def modal(cad,directory,parameters,progress):
    from opensim.modal import solve_modal
    result = solve_modal(cad, directory / "modal", size=parameters["mesh_size_m"],
                         scale=parameters["cad_scale"], young=parameters["young_Pa"],
                         poisson=parameters["poisson"], density=parameters["density_kg_m3"],
                         mode_count=parameters["mode_count"], order=parameters["element_order"], support_region=parameters["support_region"], progress=progress)

    return result


def convergence(cad,directory,parameters,progress):
    from opensim.convergence import run_convergence
    result = run_convergence(cad, directory / "convergence", size=parameters["mesh_size_m"],
                             scale=parameters["cad_scale"], young=parameters["young_Pa"], poisson=parameters["poisson"],
                             load=parameters["load_N"], order=parameters["element_order"], load_axis=parameters["load_axis"],
                             load_kind=parameters["load_kind"], load_surface=parameters["load_surface"],
                             support_region=parameters["support_region"], load_region=parameters["load_region"],
                             levels=int(parameters["convergence_levels"]), ratio=parameters["convergence_ratio"],
                             tolerance_percent=parameters["convergence_tolerance_percent"],
                             target=parameters["convergence_target"], progress=progress, load_cases=parameters['load_cases'])

    return result


def static(cad,directory,parameters,progress):
    result = solve(cad, directory / "solve", size=parameters["mesh_size_m"],
                   scale=parameters["cad_scale"], young=parameters["young_Pa"],
                   poisson=parameters["poisson"], load=parameters["load_N"], order=parameters["element_order"],
                   load_axis=parameters["load_axis"], load_kind=parameters["load_kind"], load_surface=parameters["load_surface"],
                   support_region=parameters["support_region"], load_region=parameters["load_region"], progress=progress, load_cases=parameters['load_cases'])

    return result
