"""Local complete-cost harness; outputs stay outside the product tree."""
import argparse
import ctypes
from ctypes import wintypes
from hashlib import sha256
from pathlib import Path
from time import perf_counter
import json
import os
import platform
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def peak_working_set():
    class Counters(ctypes.Structure):
        _fields_ = [("cb", wintypes.DWORD), ("faults", wintypes.DWORD)] + [
            (name, ctypes.c_size_t) for name in (
                "peak", "working", "paged_peak", "paged", "nonpaged_peak",
                "nonpaged", "pagefile", "pagefile_peak")]
    counters = Counters()
    counters.cb = ctypes.sizeof(counters)
    call = ctypes.windll.psapi.GetProcessMemoryInfo
    call.argtypes = [wintypes.HANDLE, ctypes.POINTER(Counters), wintypes.DWORD]
    if not call(wintypes.HANDLE(-1), ctypes.byref(counters), counters.cb):
        raise ctypes.WinError()
    return counters.peak


def worker(options):
    sys.path[:0] = [str(options.source / "src"), str(ROOT / "tests")]
    from test_stable_volume import build_case, upper_costs
    from homology_operator import OperatorFamilyResult, ChainWindow, QueryResult, ResourceLimits, minimum_filling
    from homology_operator import validation
    corpus_path = ROOT / "tests/fixtures/geometry_queries.json"
    phases = {}
    def timed(name, action):
        start = perf_counter()
        value = action()
        phases[name] = perf_counter() - start
        return value
    total_start = perf_counter()
    cases = timed("source_conversion", lambda: json.loads(corpus_path.read_text())["cases"])
    if options.case.startswith("fan"):
        from itertools import combinations
        n = int(options.case[3:])
        faces = [(0, i, i+1) for i in range(1, n-1)]
        cells = sorted({s for t in faces for r in range(1, 4) for s in combinations(t,r)}, key=lambda s:(len(s),s))
        case = {"id": options.case, "degree": 1, "simplices": cells,
                "levels": [0 if len(s)==1 else 1 if len(s)==2 else 3 for s in cells]}
    else:
        case = next(c for c in cases if c["id"] == options.case)
    case_hash = sha256(json.dumps(case,sort_keys=True,separators=(",",":")).encode()).hexdigest()
    family = timed("construction", lambda: build_case(case))
    def prepare():
        refs = [r for r in family.features().value if r["death_stage"] is not None]
        ref = max(refs, key=lambda r:r["death_stage"])
        return ref, upper_costs(family,ref)
    ref, upper = timed("history_pair_preparation", prepare)
    epsilon = 2 if options.case.startswith("fan") else 1
    limits = ResourceLimits(state_limit=0) if options.mode == "exhausted" else ResourceLimits()
    if options.mode == "unsupported":
        limits = ResourceLimits(packed_word_limit=10)
    def query():
        seed=family.resolve_feature(ref,ref['birth_stage']).value['representative']
        class_result=timed('class_minimum', lambda:family.stage(ref['birth_stage']).minimum_class_mass(seed))
        birth=timed('birth_pair_cycle', lambda:family.optimal_1_cycle(ref))
        ordinary=timed('ordinary_pair_volume', lambda:family.optimal_volume(ref,upper))
        fixed=(timed('fixed_boundary_filling', lambda:minimum_filling(family.windows[ref['death_stage']],ordinary.value['boundary'],upper))
               if ordinary.state=='Computed' else QueryResult('Unavailable',details={'reason':'ordinary pair boundary unavailable; dependent query not run'}))
        stable=timed('stable_volume', lambda:family.stable_volume(ref,epsilon,upper,epsilon_unit='level',limits=limits))
        return {'class':class_result,'birth':birth,'ordinary':ordinary,'fixed':fixed,'stable':stable}
    if options.mode == "warm":
        query()
        phases = {}
        total_start = perf_counter()
    replay_times, location_times = [], []
    validate = validation.validate_optimal_volume
    locate = ChainWindow.locate_chain
    def replay(*args, **kwargs):
        start = perf_counter()
        try:
            return validate(*args, **kwargs)
        finally:
            replay_times.append(perf_counter()-start)
    def location(*args, **kwargs):
        start = perf_counter()
        try:
            return locate(*args, **kwargs)
        finally:
            location_times.append(perf_counter()-start)
    validation.validate_optimal_volume = replay
    ChainWindow.locate_chain = location
    bundle = timed("query_including_validation_and_location", query)
    result=bundle['stable']
    validation.validate_optimal_volume = validate
    ChainWindow.locate_chain = locate
    phases["nested_independent_validation"] = sum(replay_times)
    phases["nested_location_export"] = sum(location_times)
    phases["nested_search_and_output"] = result.details["resource_usage"]["wall_time"]
    payload = timed("storage", lambda: json.dumps({
        "family":family.to_result().to_dict(), "upper":upper.to_dict(),
        "queries":{key:q.to_dict() for key,q in bundle.items()}}, separators=(",",":")))
    def restore():
        data=json.loads(payload)
        recovered=OperatorFamilyResult.from_dict(data["family"]).to_family()
        costs=ChainWindow.from_dict(data["upper"])
        records={key:QueryResult.from_dict(value) for key,value in data['queries'].items()}
        validation.validate_stable_volume(recovered,ref,epsilon,costs,records['stable'],epsilon_unit="level")
        validation.validate_optimal_volume(recovered,ref,costs,records['ordinary'])
        if records['ordinary'].state=='Computed':
            validation.validate_minimum_filling(recovered.windows[ref['death_stage']],records['ordinary'].value['boundary'],costs,records['fixed'])
        validation.validate_optimal_1_cycle(recovered,ref,records['birth'])
        validation.validate_minimum_class_query(recovered.windows[ref['birth_stage']],recovered.stage(ref['birth_stage']).P,records['class'])
    timed("restoration_including_independent_query_validation",restore)
    total=perf_counter()-total_start
    output={key:{"state":q.state,"exact":q.exact,"certificate_level":q.details.get("certificate_level"),
        "value":q.to_dict()["value"],"representative":q.to_dict()['details'].get('representative'),
        "guarantee":q.details.get("guarantee_level")} for key,q in bundle.items()}
    print(json.dumps({"case":options.case,"mode":options.mode,"source":str(options.source),
        "source_hashes":{p.name:sha256(p.read_bytes()).hexdigest() for p in (options.source/"src/homology_operator").glob('*.py')},
        "fixture_sha256":sha256(corpus_path.read_bytes()).hexdigest(),"input_sha256":case_hash,
        "epsilon":epsilon,"budget":result.to_dict()["details"]["resource_usage"]["limits"],
        "states":result.details["resource_usage"]["states"],
        "verification":dict(result.details["verification"]), "output":output,
        "total_seconds":total,"phases_seconds":phases,"stored_bytes":len(payload.encode()),
        "process_peak_working_set_bytes":peak_working_set(),
        "environment":{"python":sys.version,"platform":platform.platform(),"processor":platform.processor()},
        "harness_sha256":sha256(Path(__file__).read_bytes()).hexdigest()}))


if __name__ == "__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("--source",type=Path,default=ROOT)
    parser.add_argument("--case",default="T2")
    parser.add_argument("--mode",default="cold")
    options=parser.parse_args()
    worker(options)
