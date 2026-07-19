"""Round-trip tests for the mapping file."""

from __future__ import annotations

from pcos_harmonizer.mapping.io import read_mapping_file, write_mapping_file
from pcos_harmonizer.mapping.model import JoinSpec, MappingEntry, MappingFile


def test_round_trip(tmp_path):
    mf = MappingFile(
        source_dataset="nhanes",
        join=JoinSpec(key="SEQN", files=["P_RHQ.xpt"]),
        mappings=[
            MappingEntry(
                source_file="P_RHQ.xpt",
                source_column="RHQ010",
                canonical_field="age_at_menarche",
                unit_raw="years",
                unit_canonical="years",
                mapping_confidence=0.9,
                source="override",
            ),
            MappingEntry(
                source_file="P_RHQ.xpt",
                source_column="RHQ031",
                canonical_field="irregular_cycles_self_report",
                value_map={"1": True, "2": False},
                source="heuristic",
            ),
        ],
    )
    path = tmp_path / "mapping.yaml"
    write_mapping_file(mf, path)
    loaded = read_mapping_file(path)

    assert loaded.join.key == "SEQN"
    assert len(loaded.mappings) == 2
    assert loaded.mappings[1].value_map == {"1": True, "2": False}
    assert len(loaded.active_mappings()) == 2
