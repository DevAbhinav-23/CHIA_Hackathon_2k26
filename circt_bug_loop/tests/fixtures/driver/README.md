# `fixtures/driver/`

| Path | What it is | How it was made |
|---|---|---|
| `image_spec/ok.json` | The `ImageSpec` of the image this campaign runs. | **Derived** from `analysis/measurements/raw/image-manifest.json`, which W-04 recorded from `chia-circt-assert:eade0de61bc5`: every field is that file's, `tool_hashes` flattened by `bug_loop.parse_hash_manifest`, and `lit_discovery_ok` and `lit_discovered_count` read by `bug_loop.lit_discovery` off `fixtures/image/lit_show_tests.txt`. `cmake_args` and `assertion_nonreferencing` are empty: the recorded manifest carries neither. |
| `image_spec/lit_broken.json` | The same spec with `lit_discovery_ok` false and the count zero. | **Derived** from `ok.json` by `dataclasses.replace`, which is pre-flight check 6's refusing half. |

The pre-flight checks take fixture stores, explicit environment mappings and
throwaway git repositories built in `tmp_path`; none of the twelve needs a
committed repository fixture, which is why there is no `repo/` here.
