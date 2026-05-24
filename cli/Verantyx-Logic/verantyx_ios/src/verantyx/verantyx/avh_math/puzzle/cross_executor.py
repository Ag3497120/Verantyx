from avh_math.puzzle.cross_to_ir import cross_to_ir
from avh_math.puzzle.program_runner import emit_truth_table_code, run_program
from avh_math.puzzle.status_types import ReasoningStatus

def execute_cross_verification(cross):
    """Cross の構造から検証プログラムを生成・実行し、確証を得る"""
    try:
        ir = cross_to_ir(cross)
        
        if ir.kind == "truth_table":
            code = emit_truth_table_code(ir)
            result = run_program(code)
            
            if result:
                cross.status = ReasoningStatus.PROVED
                cross.metadata["execution_method"] = "generated_truth_table"
                cross.metadata["execution_verified"] = True
            else:
                cross.status = ReasoningStatus.DISPROVED
                cross.metadata["execution_method"] = "generated_truth_table"
                cross.metadata["execution_verified"] = True
                
        # 他の kind (kripke等) も同様に拡張可能
        
    except Exception as e:
        cross.metadata["execution_error"] = str(e)
        
    return cross
