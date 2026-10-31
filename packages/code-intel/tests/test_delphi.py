"""Tests for generic Delphi/Object Pascal parser."""

from faccoder_code_intel.models import RelationshipKind, SymbolType
from faccoder_code_intel.parsers import parse_file
from faccoder_code_intel.parsers.delphi import DelphiParser


def test_delphi_unit_parsing() -> None:
    pas_code = """// Header license comment
unit OrderCalculator;

interface

uses
  SysUtils, Classes, MathUtils;

type
  IOrderValidator = interface
    function Validate(OrderId: Integer): Boolean;
  end;

  TOrderCalculator = class(TObject, IOrderValidator)
  private
    FTotal: Double;
  public
    constructor Create;
    destructor Destroy; override;
    function CalculateDiscount(BasePrice: Double; Rate: Double): Double;
    property Total: Double;
  end;

implementation

{ TOrderCalculator }

constructor TOrderCalculator.Create;
begin
  inherited Create;
  FTotal := 0.0;
end;

destructor TOrderCalculator.Destroy;
begin
  inherited Destroy;
end;

// Calculates discount based on rate
function TOrderCalculator.CalculateDiscount(BasePrice: Double; Rate: Double): Double;
var
  DiscountAmount: Double;
begin
  DiscountAmount := BasePrice * Rate;
  Result := BasePrice - DiscountAmount;
end;

end.
"""
    parser = DelphiParser()
    symbols = parser.parse(pas_code, file_path="OrderCalculator.pas")

    names = {s.name: s for s in symbols}
    assert "OrderCalculator" in names
    unit_sym = names["OrderCalculator"]
    assert unit_sym.symbol_type == SymbolType.MODULE
    assert RelationshipKind.USES in unit_sym.relationships
    assert "SysUtils" in unit_sym.relationships[RelationshipKind.USES]
    assert "MathUtils" in unit_sym.relationships[RelationshipKind.USES]

    assert "IOrderValidator" in names
    assert names["IOrderValidator"].symbol_type == SymbolType.INTERFACE

    assert "TOrderCalculator" in names
    calc_class = names["TOrderCalculator"]
    assert calc_class.symbol_type == SymbolType.CLASS
    assert "TObject" in calc_class.relationships[RelationshipKind.INHERITS]
    assert "IOrderValidator" in calc_class.relationships[RelationshipKind.IMPLEMENTS]

    assert "Total" in names
    assert names["Total"].symbol_type == SymbolType.PROPERTY

    # Implementation routines
    qnames = {s.qualified_name: s for s in symbols}
    assert "TOrderCalculator.Create" in qnames
    assert qnames["TOrderCalculator.Create"].symbol_type == SymbolType.CONSTRUCTOR

    assert "TOrderCalculator.Destroy" in qnames
    assert qnames["TOrderCalculator.Destroy"].symbol_type == SymbolType.DESTRUCTOR

    assert "TOrderCalculator.CalculateDiscount" in qnames
    fn_sym = qnames["TOrderCalculator.CalculateDiscount"]
    assert fn_sym.symbol_type == SymbolType.METHOD
    assert fn_sym.signature.return_type == "Double"
    assert len(fn_sym.signature.parameters) == 2
    assert fn_sym.signature.parameters[0].name == "BasePrice"
    assert fn_sym.docstring == "Calculates discount based on rate"
    assert "Result := BasePrice - DiscountAmount;" in fn_sym.body


def test_delphi_dfm_parsing() -> None:
    dfm_content = """object MainForm: TMainForm
  Left = 200
  Top = 150
  Caption = 'Order Processing'
  ClientHeight = 400
  ClientWidth = 600
  object btnSubmit: TButton
    Left = 50
    Top = 100
    Width = 75
    Height = 25
    Caption = 'Submit'
  end
  object edtCustomer: TEdit
    Left = 50
    Top = 50
    Width = 120
    Height = 21
  end
end
"""
    symbols = parse_file("MainForm.dfm", content=dfm_content)
    names = {s.name: s for s in symbols}

    assert "MainForm" in names
    assert names["MainForm"].symbol_type == SymbolType.DFM_OBJECT
    assert names["MainForm"].metadata["component_type"] == "TMainForm"

    assert "btnSubmit" in names
    assert names["btnSubmit"].metadata["component_type"] == "TButton"

    assert "edtCustomer" in names
    assert names["edtCustomer"].metadata["component_type"] == "TEdit"
