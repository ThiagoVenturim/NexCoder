"""Tests for BottomUpDocEngine hierarchical documentation generation."""

from langchain_core.language_models.fake_chat_models import FakeListChatModel
from nexcoder_code_intel.docgen import BottomUpDocEngine, DocLevel
from nexcoder_code_intel.graph import Community
from nexcoder_code_intel.models import (
    Symbol,
    SymbolLocation,
    SymbolParameter,
    SymbolSignature,
    SymbolType,
)


def test_bottom_up_doc_generation() -> None:
    # 1. Level 0 Routine
    fn_loc = SymbolLocation(file_path="src/calc.py", start_line=10, end_line=15)
    fn_sig = SymbolSignature(
        raw="def add(a: int, b: int) -> int",
        name="add",
        parameters=[
            SymbolParameter(name="a", type_annotation="int"),
            SymbolParameter(name="b", type_annotation="int"),
        ],
        return_type="int",
    )
    fn_sym = Symbol(
        id="src/calc.py::add:10",
        name="add",
        qualified_name="Calculator.add",
        symbol_type=SymbolType.METHOD,
        location=fn_loc,
        language="python",
        signature=fn_sig,
        docstring="Adds two integers.",
        parent_id="src/calc.py::Calculator:1",
    )

    # Level 1 Class
    cls_loc = SymbolLocation(file_path="src/calc.py", start_line=1, end_line=20)
    cls_sym = Symbol(
        id="src/calc.py::Calculator:1",
        name="Calculator",
        qualified_name="Calculator",
        symbol_type=SymbolType.CLASS,
        location=cls_loc,
        language="python",
        docstring="Mathematical calculator service.",
    )

    # Level 2 Module
    mod_sym = Symbol(
        id="src/calc.py::module",
        name="calc",
        qualified_name="calc",
        symbol_type=SymbolType.MODULE,
        location=cls_loc,
        language="python",
        relationships={"uses": ["math", "sys"]},
    )

    engine = BottomUpDocEngine()

    # Community Level 3
    comm = Community(
        id=1,
        title="Math Subsystem",
        summary="Handles numerical computations.",
        symbols=[fn_sym.id, cls_sym.id],
    )

    tree = engine.generate_tree([mod_sym, cls_sym, fn_sym], communities=[comm])

    assert fn_sym.id in tree
    routine_node = tree[fn_sym.id]
    assert routine_node.level == DocLevel.ROUTINE
    assert "Adds two integers." in routine_node.markdown
    assert "`a`: int" in routine_node.markdown

    assert cls_sym.id in tree
    cls_node = tree[cls_sym.id]
    assert cls_node.level == DocLevel.CLASS
    assert "Calculator" in cls_node.markdown
    assert "add" in cls_node.markdown

    assert "src/calc.py::module" in tree
    mod_node = tree["src/calc.py::module"]
    assert mod_node.level == DocLevel.MODULE
    assert "Calculator" in mod_node.markdown

    assert "system::architecture" in tree
    sys_node = tree["system::architecture"]
    assert sys_node.level == DocLevel.SYSTEM
    assert "Math Subsystem" in sys_node.markdown


def test_docgen_exact_member_matching_and_dotted_standalone() -> None:
    """Ensure class member matching is exact and dotted helper functions remain at module level."""
    loc = SymbolLocation(file_path="auth.py", start_line=1, end_line=50)

    # Classes: "User" and "UserProfile"
    user_cls = Symbol(
        id="auth.py::User",
        name="User",
        qualified_name="User",
        symbol_type=SymbolType.CLASS,
        location=loc,
        language="python",
    )
    user_prof_cls = Symbol(
        id="auth.py::UserProfile",
        name="UserProfile",
        qualified_name="UserProfile",
        symbol_type=SymbolType.CLASS,
        location=loc,
        language="python",
    )

    # Method for User
    user_method = Symbol(
        id="auth.py::User.get_id",
        name="get_id",
        qualified_name="User.get_id",
        symbol_type=SymbolType.METHOD,
        location=loc,
        language="python",
    )
    # Method for UserProfile (contains "User" as substring prefix)
    prof_method = Symbol(
        id="auth.py::UserProfile.get_bio",
        name="get_bio",
        qualified_name="UserProfile.get_bio",
        symbol_type=SymbolType.METHOD,
        location=loc,
        language="python",
    )
    # Standalone function with dotted qualified_name (e.g. module.helper)
    helper_fn = Symbol(
        id="auth.py::auth.hash_password",
        name="hash_password",
        qualified_name="auth.hash_password",
        symbol_type=SymbolType.FUNCTION,
        location=loc,
        language="python",
    )

    engine = BottomUpDocEngine()
    tree = engine.generate_tree([user_cls, user_prof_cls, user_method, prof_method, helper_fn])

    # User class should only have User.get_id, NOT UserProfile.get_bio
    user_doc = tree[user_cls.id]
    assert user_doc.details["members_count"] == 1
    assert user_method.id in user_doc.details["member_ids"]
    assert prof_method.id not in user_doc.details["member_ids"]

    # UserProfile class should have UserProfile.get_bio
    prof_doc = tree[user_prof_cls.id]
    assert prof_doc.details["members_count"] == 1
    assert prof_method.id in prof_doc.details["member_ids"]

    # Module doc should contain standalone dotted helper_fn
    mod_doc = tree["auth.py::module"]
    assert helper_fn.name in mod_doc.markdown


def test_docgen_with_llm_synthesis() -> None:
    """Ensure LLM is invoked when provided to synthesize custom summaries."""
    loc = SymbolLocation(file_path="service.py", start_line=1, end_line=20)
    fn_sym = Symbol(
        id="service.py::process",
        name="process",
        qualified_name="process",
        symbol_type=SymbolType.FUNCTION,
        location=loc,
        language="python",
        docstring="Initial docstring",
    )

    fake_llm = FakeListChatModel(responses=["LLM-synthesized summary for process."])
    engine = BottomUpDocEngine(llm=fake_llm)

    node = engine.document_routine(fn_sym)
    assert node.summary == "LLM-synthesized summary for process."
    assert "LLM-synthesized summary for process." in node.markdown
