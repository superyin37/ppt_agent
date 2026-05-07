from agent.outline import (
    _SlotAssignmentLLM,
    _expanded_blueprint_slots,
    _normalize_assignment_order,
)
from agent.material_binding import _collect_required_patterns
from schema.outline import OutlineSlideEntry


EXPECTED_CONCEPT_ORDER = [
    "concept-intro-1",
    "concept-aerial-1",
    "concept-perspective-1",
    "concept-intro-2",
    "concept-aerial-2",
    "concept-perspective-2",
    "concept-intro-3",
    "concept-aerial-3",
    "concept-perspective-3",
]


def _assignment(slot_id: str, slide_no: int) -> _SlotAssignmentLLM:
    return _SlotAssignmentLLM(
        slot_id=slot_id,
        slide_no=slide_no,
        section="concept",
        title=slot_id,
        content_directive=slot_id,
    )


def test_blueprint_expands_concept_pages_by_scheme():
    slot_ids = [slot_id for slot_id, _title, _slot in _expanded_blueprint_slots(reference_count=3)]
    concept_slot_ids = [slot_id for slot_id in slot_ids if slot_id.startswith("concept-")]

    assert concept_slot_ids == EXPECTED_CONCEPT_ORDER


def test_outline_normalization_reorders_legacy_concept_grouping():
    assignments = [
        _assignment("cover", 1),
        _assignment("concept-intro-1", 2),
        _assignment("concept-intro-2", 3),
        _assignment("concept-intro-3", 4),
        _assignment("concept-aerial-1", 5),
        _assignment("concept-aerial-2", 6),
        _assignment("concept-aerial-3", 7),
        _assignment("concept-perspective-1", 8),
        _assignment("concept-perspective-2", 9),
        _assignment("concept-perspective-3", 10),
        _assignment("material-economic", 11),
    ]

    normalized = _normalize_assignment_order(assignments)

    assert [a.slot_id for a in normalized[1:10]] == EXPECTED_CONCEPT_ORDER
    assert [a.slide_no for a in normalized] == list(range(1, len(normalized) + 1))
    assert normalized[-1].slot_id == "material-economic"


def test_concept_material_binding_uses_scheme_specific_assets():
    aerial_entry = OutlineSlideEntry(
        slot_id="concept-aerial-2",
        slide_no=1,
        section="concept",
        title="aerial",
        purpose="",
        key_message="",
        required_input_keys=["brief_doc", "concept_description", "concept_aerial"],
    )
    perspective_entry = OutlineSlideEntry(
        slot_id="concept-perspective-3",
        slide_no=2,
        section="concept",
        title="perspective",
        purpose="",
        key_message="",
        required_input_keys=["concept_ext_perspective", "concept_int_perspective"],
    )

    assert _collect_required_patterns(aerial_entry) == ["concept.2.aerial"]
    assert _collect_required_patterns(perspective_entry) == [
        "concept.3.ext_perspective",
        "concept.3.int_perspective",
    ]
