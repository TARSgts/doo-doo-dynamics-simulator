"""Lightweight load validation; never initializes a numerical runtime in MCP."""
import math
from opensim.region_settings import validate_region
from opensim.load_settings import LOAD_SURFACES


def validate_load_cases(cases):
    if not isinstance(cases,list) or len(cases)>32:raise ValueError('Use at most 32 independent loads')
    for item in cases:
        if not isinstance(item,dict) or set(item)-{'name','kind','components_N','pressure_Pa','region','surface','enabled'}:raise ValueError('Invalid independent load fields')
        if not isinstance(item.get('name',''),str) or len(item.get('name',''))>80:raise ValueError('Load names must be at most 80 characters')
        if item.get('kind') not in {'force','pressure'} or item.get('surface','x-max') not in LOAD_SURFACES:raise ValueError('Choose a surface force or pressure and a valid fallback surface')
        if not isinstance(item.get('enabled',True),bool):raise ValueError('Load enabled flag must be boolean')
        validate_region(item.get('region',{}))
        values=item.get('components_N',[0,0,0]) if item['kind']=='force' else [item.get('pressure_Pa',0)]
        if not isinstance(values,list) or len(values)!=(3 if item['kind']=='force' else 1):raise ValueError('Each force needs its own X/Y/Z components')
        if any(isinstance(v,bool) or not isinstance(v,(int,float)) or not math.isfinite(v) for v in values):raise ValueError('Load values must be finite numbers')
        if item.get('enabled',True) and not any(values):raise ValueError('An enabled load must be nonzero')
    if cases and not any(c.get('enabled',True) for c in cases):raise ValueError('Enable at least one load or clear the list to use the legacy load')
