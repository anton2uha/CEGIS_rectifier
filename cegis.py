"""
CEGIS (Counter-Example Guided Inductive Synthesis) implementation.

"""

from z3 import Solver, sat, unsat, And, Not
import encoder as enc_module


def run(encoding: dict, max_iterations: int = 10000, verbose: bool = False) -> dict:
    """
    Run the CEGIS loop to find parameter values.
    
    Args:
        encoding: Dictionary from encoder.encode()
        
    Returns:
        Dictionary with:
            - success: True if solution found
            - model: Z3 model (if success)
            - iterations: number of iterations used
            - test_vectors: list of counterexamples found
            - reason: failure reason (if not success)
    """
    params = encoding['params']
    inputs = encoding['inputs']
    behavior = encoding['behavior']
    correctness = encoding['correctness']
    impl_circuit = encoding['impl_circuit']
    spec_circuit = encoding['spec_circuit']
    param_info = encoding['param_info']
    input_names = encoding['input_names']
    output_names = encoding['output_names']
    
    synth = Solver()
    test_vectors = []
    
    for iteration in range(1, max_iterations + 1):
        if verbose:
            print(f"  Iteration {iteration}...")
        
        #Find params that work for all known test vectors
        result = synth.check()
        if result == unsat:
            return {'success': False, 'iterations': iteration,
                    'reason': 'No valid parameters exist for the given gates'}
        
        candidate = synth.model()
        
        # Check if candidate works for ALL inputs
        verifier = Solver()
        verifier.add(behavior)
        verifier.add(And([p == candidate.eval(p, model_completion=True) for p in params]))
        verifier.add(Not(correctness))
        
        result = verifier.check()
        if result == unsat:

            return {'success': True, 'model': candidate, 
                    'iterations': iteration, 'test_vectors': test_vectors}
        
        counterexample = verifier.model()
        
        # Extract concrete input values from counterexample
        input_values = {}
        for name, var in zip(input_names, inputs):
            input_values[name] = bool(counterexample.eval(var, model_completion=True))
        
        test_vectors.append(input_values)
        print(f"    Primary inputs: {input_values}") 
        if verbose:
            print(f"    Counterexample: {input_values}")
        
        # Evaluate circuits with concrete inputs
        impl_values = enc_module.evaluate_circuit(impl_circuit, input_values)
        spec_values = enc_module.evaluate_circuit(spec_circuit, input_values)
        
        # Add constraints directly on parameters
        constraints = []
        for gate_name, gate_params in param_info.items():
            gate = impl_circuit.get_gate(gate_name)
            gate_input_values = [impl_values[inp] for inp in gate.inputs]
             
            
            spec_gate = spec_circuit.get_gate(gate_name)
            expected_output = enc_module.evaluate_gate(spec_gate.truth_table, gate_input_values)
            print(f"    Gate {gate_name} sees inputs: {gate_input_values}")
            print(f"    Expected output (from spec truth table): {expected_output}")

            
            constraint = enc_module.get_parameterized_constraint(
                gate_input_values, expected_output, gate_params)
            constraints.append(constraint)
        
        synth.add(And(constraints) if len(constraints) > 1 else constraints[0])
        
    # Timeout
    return {'success': False, 'iterations': max_iterations, 'reason': 'Maximum iterations reached'}


# Testing (example blif)
if __name__ == "__main__":
    import blif_parser
    import encoder
    
    # Buggy circuit: AND instead of OR
    impl_blif = """
    .model impl
    .inputs a b
    .outputs f
    .names a b f
    11 1
    .end
    """
    
    # Correct circuit: OR
    spec_blif = """
    .model spec
    .inputs a b
    .outputs f
    .names a b f
    1- 1
    -1 1
    .end
    """
    
    impl = blif_parser.parse_string(impl_blif)
    spec = blif_parser.parse_string(spec_blif)
    
    print("Testing CEGIS...")
    print(f"  Impl: {impl.gates[0].truth_table.identify_gate_type()}")
    print(f"  Spec: {spec.gates[0].truth_table.identify_gate_type()}")
    
    enc = encoder.encode(impl, spec, gates_to_fix={'f'})
    
    result = run(enc, verbose=True)
    
    print(f"\nResult: {'SUCCESS' if result['success'] else 'FAILED'}")
    print(f"Iterations: {result['iterations']}")
    
    if result['success']:
        fixes = encoder.extract_solution(result['model'], enc['param_info'])
        for gate, info in fixes.items():
            print(f"  Gate '{gate}' -> {info['gate_type']}")
    else:
        print(f"Reason: {result['reason']}")

