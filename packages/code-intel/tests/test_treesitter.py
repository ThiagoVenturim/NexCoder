"""Tests for Tree-sitter parsers across supported languages."""

from faccoder_code_intel.models import RelationshipKind, SymbolType
from faccoder_code_intel.parsers import get_parser_for_file, parse_file
from faccoder_code_intel.parsers.treesitter import TreeSitterParser


def test_python_parsing() -> None:
    code = '''"""Module docstring."""

class BaseHandler:
    pass

class OrderProcessor(BaseHandler):
    """Processes incoming orders."""

    async def process_order(self, order_id: str) -> bool:
        """Process a single order."""
        return True

def standalone_helper(x: int) -> int:
    return x * 2
'''
    parser = TreeSitterParser(["python"])
    symbols = parser.parse(code, file_path="order_service.py")

    names = {s.name: s for s in symbols}
    assert "BaseHandler" in names
    assert "OrderProcessor" in names
    assert "process_order" in names
    assert "standalone_helper" in names

    proc = names["OrderProcessor"]
    assert proc.symbol_type == SymbolType.CLASS
    assert proc.docstring == "Processes incoming orders."
    assert RelationshipKind.INHERITS in proc.relationships
    assert "BaseHandler" in proc.relationships[RelationshipKind.INHERITS]

    method = names["process_order"]
    assert method.symbol_type == SymbolType.METHOD
    assert method.qualified_name == "OrderProcessor.process_order"
    assert method.docstring == "Process a single order."
    assert "async" in method.signature.modifiers

    helper = names["standalone_helper"]
    assert helper.symbol_type == SymbolType.FUNCTION


def test_go_parsing() -> None:
    code = """package service

type Repository interface {
    Get(id string) (string, error)
}

type UserService struct {
    repo Repository
}

// Greet returns a greeting for the user.
func (s *UserService) Greet(name string) string {
    return "Hello " + name
}

func NewService(repo Repository) *UserService {
    return &UserService{repo: repo}
}
"""
    symbols = parse_file("service.go", content=code)
    names = {s.name: s for s in symbols}

    assert "Repository" in names
    assert names["Repository"].symbol_type == SymbolType.INTERFACE

    assert "UserService" in names
    assert names["UserService"].symbol_type == SymbolType.STRUCT

    assert "Greet" in names
    assert names["Greet"].symbol_type == SymbolType.METHOD
    assert names["Greet"].qualified_name == "UserService.Greet"

    assert "NewService" in names
    assert names["NewService"].symbol_type == SymbolType.FUNCTION


def test_typescript_parsing() -> None:
    code = """export interface UserAccount {
    id: string;
    balance: number;
}

export class AccountManager extends BaseManager {
    // Calculates total fee
    calculateFee(amount: number): number {
        return amount * 0.05;
    }
}
"""
    symbols = parse_file("account.ts", content=code)
    names = {s.name: s for s in symbols}

    assert "UserAccount" in names
    assert names["UserAccount"].symbol_type == SymbolType.INTERFACE

    assert "AccountManager" in names
    assert names["AccountManager"].symbol_type == SymbolType.CLASS
    assert "BaseManager" in names["AccountManager"].relationships[RelationshipKind.INHERITS]

    assert "calculateFee" in names
    assert names["calculateFee"].symbol_type == SymbolType.METHOD


def test_java_parsing() -> None:
    code = """package com.example;

public class PaymentGateway extends BaseGateway implements IPayment {
    public PaymentGateway() {}

    public boolean charge(double amount) {
        return true;
    }
}
"""
    symbols = parse_file("PaymentGateway.java", content=code)
    qnames = {s.qualified_name: s for s in symbols}

    assert "PaymentGateway" in qnames
    gw = qnames["PaymentGateway"]
    assert gw.symbol_type == SymbolType.CLASS
    assert "BaseGateway" in gw.relationships[RelationshipKind.INHERITS]
    assert "IPayment" in gw.relationships[RelationshipKind.IMPLEMENTS]

    assert "PaymentGateway.PaymentGateway" in qnames
    assert qnames["PaymentGateway.PaymentGateway"].symbol_type == SymbolType.CONSTRUCTOR

    assert "PaymentGateway.charge" in qnames
    assert qnames["PaymentGateway.charge"].symbol_type == SymbolType.METHOD


def test_cpp_parsing() -> None:
    code = """class VectorMath : public BaseMath {
public:
    double dotProduct(double a, double b);
};

int computeSum(int a, int b) {
    return a + b;
}
"""
    symbols = parse_file("math_engine.cpp", content=code)
    names = {s.name: s for s in symbols}

    assert "VectorMath" in names
    assert names["VectorMath"].symbol_type == SymbolType.CLASS
    assert "BaseMath" in names["VectorMath"].relationships[RelationshipKind.INHERITS]

    assert "computeSum" in names
    assert names["computeSum"].symbol_type == SymbolType.FUNCTION


def test_rust_parsing() -> None:
    code = """pub struct CacheConfig {
    pub ttl: u64,
}

pub trait Storage {
    fn flush(&self);
}

impl CacheConfig {
    pub fn new(ttl: u64) -> Self {
        Self { ttl }
    }
}

pub fn init_cache() -> bool {
    true
}
"""
    symbols = parse_file("cache.rs", content=code)
    names = {s.name: s for s in symbols}

    assert "CacheConfig" in names
    assert names["CacheConfig"].symbol_type == SymbolType.STRUCT

    assert "Storage" in names
    assert names["Storage"].symbol_type == SymbolType.INTERFACE

    assert "new" in names
    assert names["new"].qualified_name == "CacheConfig::new"

    assert "init_cache" in names
    assert names["init_cache"].symbol_type == SymbolType.FUNCTION


def test_unsupported_file() -> None:
    parser = get_parser_for_file("notes.txt")
    assert parser is None


def test_typescript_arrow_functions() -> None:
    code = """// Helper to calculate total
export const calculateTotal = (subtotal: number, taxRate: number): number => {
    return subtotal * (1 + taxRate);
};

const formatCurrency = (amount: number): string => `$${amount.toFixed(2)}`;
"""
    symbols = parse_file("utils.ts", content=code)
    names = {s.name: s for s in symbols}

    assert "calculateTotal" in names
    fn = names["calculateTotal"]
    assert fn.symbol_type == SymbolType.FUNCTION
    assert fn.docstring == "Helper to calculate total"
    assert len(fn.signature.parameters) == 2

    assert "formatCurrency" in names
    assert names["formatCurrency"].symbol_type == SymbolType.FUNCTION
