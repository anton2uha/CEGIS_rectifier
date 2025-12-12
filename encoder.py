"""
Z3 encoder for circuits.

Converts Circuit objects into Z3 boolean formulas for CEGIS-based rectification.
"""

from z3 import Bool, And, Or, Not, If, Implies, BoolRef
from circuit_types import Circuit, Gate, TruthTable


# Gate Encoding

def encode_fixed_gate(inputs: list[BoolRef], tt: TruthTable) -> BoolRef:
    """
    Encode a gate with a fixed truth table.
    """
    if tt.num_inputs == 0:
        # Constant gate
        return len(tt.onset_cubes) > 0  # True if onset is non-empty
    
    # Build sum of products from onset cubes
    terms = []
    
    for cube in tt.onset_cubes:
        # Build product term for this cube
        literals = []
        for i, c in enumerate(cube):
            if c == '1':
                literals.append(inputs[i])
            elif c == '0':
                literals.append(Not(inputs[i]))
            # '-' = don't care, skip
        
        if literals:
            terms.append(And(*literals) if len(literals) > 1 else literals[0])
        else:
            # Empty cube (all don't-cares) = always true
            terms.append(True)
    
    if not terms:
        return False  # Empty onset = constant 0
    
    return Or(*terms) if len(terms) > 1 else terms[0]


def encode_parameterized_gate(inputs: list[BoolRef], params: list[BoolRef]) -> BoolRef:
    """
    Encode a fully parameterized gate.
    
    For 2-input gates: 4 parameters [p0, p1, p2, p3] encode the truth table.
        p0 = f(0,0), p1 = f(0,1), p2 = f(1,0), p3 = f(1,1)
    
    For 1-input gates: 2 parameters [p0, p1]
        p0 = f(0), p1 = f(1)
        
    """
    if len(inputs) == 2:
        if len(params) != 4:
            raise ValueError("2-input gate requires 4 parameters")
        a, b = inputs
        # output = a ? (b ? p3 : p2) : (b ? p1 : p0)
        return If(a, If(b, params[3], params[2]), If(b, params[1], params[0]))
    
    elif len(inputs) == 1:
        if len(params) != 2:
            raise ValueError("1-input gate requires 2 parameters")
        a = inputs[0]
        # output = a ? p1 : p0
        return If(a, params[1], params[0])
    
    elif len(inputs) == 0:
        if len(params) != 1:
            raise ValueError("0-input gate requires 1 parameter")
        return params[0]
    
    else:
        raise ValueError(f"Gates with {len(inputs)} inputs not supported for parameterization")


def params_to_gate_type(param_values: list[bool]) -> str:
    """
    Convert parameter values to human-readable gate type.
    """
    tt = ''.join('1' if p else '0' for p in param_values)
    
    gate_types = {
        # 2-input (4 params)
        "0000": "CONST0",
        "0001": "AND",
        "0010": "A_AND_NOT_B",
        "0011": "BUF_A",
        "0100": "NOT_A_AND_B",
        "0101": "BUF_B",
        "0110": "XOR",
        "0111": "OR",
        "1000": "NOR",
        "1001": "XNOR",
        "1010": "NOT_B",
        "1011": "A_OR_NOT_B",
        "1100": "NOT_A",
        "1101": "NOT_A_OR_B",
        "1110": "NAND",
        "1111": "CONST1",
        # 1-input (2 params)
        "00": "CONST0",
        "01": "BUF",
        "10": "NOT",
        "11": "CONST1",
    }
    
    return gate_types.get(tt, f"UNKNOWN({tt})")

def evaluate_gate(tt: TruthTable, inputs: list[bool]) -> bool:
    """
    Evaluate a gate's truth table with concrete input values.
    """
    for cube in tt.onset_cubes:
        match = True
        for i, c in enumerate(cube):
            if c == '1' and not inputs[i]:
                match = False
                break
            elif c == '0' and inputs[i]:
                match = False
                break
        if match:
            return True
    return False


def evaluate_circuit(circuit: Circuit, input_values: dict[str, bool]) -> dict[str, bool]:
    """
    Evaluate a circuit with concrete input values.
    
    Args:
        circuit: The circuit to evaluate
        input_values: dict mapping input names to boolean values
        
    Returns:
        dict mapping all signal names (inputs + gates) to their computed values
    """
    values = dict(input_values)
    
    for gate in circuit.topological_sort():
        gate_inputs = [values[inp] for inp in gate.inputs]
        output = evaluate_gate(gate.truth_table, gate_inputs)
        values[gate.name] = output
    
    return values


def get_parameterized_constraint(input_values: list[bool], expected_output: bool,
                                  params: list[BoolRef]) -> BoolRef:
    """
    Get the constraint on parameters given concrete input/output values.
    
    For inputs [a, b], the truth table index is computed as:
        index = a * 2 + b (for 2 inputs)
    More generally: index = sum(input[i] * 2^(n-1-i)) for n inputs
    
    This matches the parameter ordering in encode_parameterized_gate.
    
    Args:
        input_values: Concrete boolean values for gate inputs
        expected_output: The output value the gate should produce
        params: Z3 parameter variables for this gate
        
    Returns:
        Z3 constraint on the relevant parameter
    """
    # Compute index into truth table
    # For 2 inputs [a, b]: index = a*2 + b
    # params[0] = f(0,0), params[1] = f(0,1), params[2] = f(1,0), params[3] = f(1,1)
    n = len(input_values)
    index = 0
    for i, val in enumerate(input_values):
        if val:
            index += (1 << (n - 1 - i))
    
    # The parameter at this index must equal expected output
    if expected_output:
        return params[index]
    else:
        return Not(params[index])



# Circuit Encoding

def encode(impl_circuit: Circuit, spec_circuit: Circuit, gates_to_fix: set[str]) -> dict:
    """
    Encode two circuits for CEGIS-based rectification.
    
    Creates Z3 variables and constraints for the implementation (with parameterized
    gates) and specification circuits, set up for CEGIS to find parameter values
    that make impl match spec.
    
    Args:
        impl_circuit: The buggy implementation circuit
        spec_circuit: The correct specification circuit
        gates_to_fix: Set of gate names (in impl) to parameterize
        
    Returns:
        Dictionary containing:
            'params': list of Z3 parameter variables to synthesize
            'inputs': list of Z3 primary input variables
            'behavior': Z3 expression for circuit behavior (gate equations)
            'correctness': Z3 expression (impl outputs == spec outputs)
            'param_info': dict mapping gate names to their parameter variables
            'signals': dict of all signal variables (for debugging)
            'impl_circuit': the implementation circuit
            'spec_circuit': the specification circuit
            'input_names': list of primary input names
            'output_names': list of primary output names
    """

    # Validate inputs match
    if set(impl_circuit.primary_inputs) != set(spec_circuit.primary_inputs):
        raise ValueError("Circuits have different primary inputs")
    if set(impl_circuit.primary_outputs) != set(spec_circuit.primary_outputs):
        raise ValueError("Circuits have different primary outputs")
    

    params = []           # All parameter variables
    param_info = {}       # gate_name -> [param vars]
    signals = {}          # net_name -> Z3 var (for debugging)
    constraints = []      # All behavior constraints
    
    # Create Z3 variables for primary inputs (shared between impl and spec)
    input_vars = []
    for pi in impl_circuit.primary_inputs:
        var = Bool(pi)
        signals[pi] = var
        input_vars.append(var)
    
    # Encode implementation circuit, starting with primary inputs
    impl_signals = dict(signals)

    
    for gate in impl_circuit.topological_sort():
        # Get input signals
        gate_inputs = [impl_signals[inp] for inp in gate.inputs]
        
        # Create output signal variable
        out_var = Bool(f"{gate.name}")
        impl_signals[gate.name] = out_var
        signals[gate.name] = out_var
        
        # Encode gate function
        if gate.name in gates_to_fix:
            # The number of parameters is the powerset
            num_params = 2 ** gate.num_inputs()
            gate_params = [Bool(f"p_{gate.name}_{i}") for i in range(num_params)]
            params.extend(gate_params)
            param_info[gate.name] = gate_params
            
            gate_func = encode_parameterized_gate(gate_inputs, gate_params)
        else:
            # Fixed gate!
            gate_func = encode_fixed_gate(gate_inputs, gate.truth_table)
        
        # Add constraint: output == function(inputs)
        constraints.append(out_var == gate_func)
    
    # Encode specification circuit (all fixed, separate signal namespace)
    
    #spec_signals = dict(signals)  # Start with shared primary inputs
    spec_signals = {pi: signals[pi] for pi in impl_circuit.primary_inputs}  # Only primary inputs!
    
    for gate in spec_circuit.topological_sort():
        # Get input signals (from spec namespace)
        gate_inputs = [spec_signals[inp] for inp in gate.inputs]
        
        # Create output signal variable (with _spec suffix)
        out_var = Bool(f"{gate.name}_spec")
        spec_signals[gate.name] = out_var
        signals[f"{gate.name}_spec"] = out_var
        
        # Encode fixed gate function
        gate_func = encode_fixed_gate(gate_inputs, gate.truth_table)
        
        # Add constraint
        constraints.append(out_var == gate_func)
    
    # Build correctness constraint: impl outputs == spec outputs
    correctness_terms = []
    for po in impl_circuit.primary_outputs:
        impl_out = impl_signals[po]
        spec_out = spec_signals[po]
        correctness_terms.append(impl_out == spec_out)
    
    correctness = And(*correctness_terms) if len(correctness_terms) > 1 else correctness_terms[0]
    
    # Combine all behavior constraints
    behavior = And(*constraints) if len(constraints) > 1 else constraints[0]
    
    return {
        'params': params,
        'inputs': input_vars,
        'behavior': behavior,
        'correctness': correctness,
        'param_info': param_info,
        'signals': signals,
        'impl_circuit': impl_circuit,
        'spec_circuit': spec_circuit,
        'input_names': impl_circuit.primary_inputs,
        'output_names': impl_circuit.primary_outputs,
    }


def extract_solution(model, param_info: dict) -> dict:
    """
    Extract gate fixes from a Z3 model.
    """
    fixes = {}
    
    for gate_name, gate_params in param_info.items():
        # Extract parameter values from model
        param_values = []
        for p in gate_params:
            val = model.eval(p, model_completion=True)
            param_values.append(bool(val))
        
        # Convert to gate type
        gate_type = params_to_gate_type(param_values)
        fixes[gate_name] = {
            'params': param_values,
            'gate_type': gate_type
        }
    
    return fixes


# Testing

if __name__ == "__main__":
    from z3 import Solver, sat
    import blif_parser
    
    # Create a simple test case
    spec_blif = """
    .model spec
    .inputs a b
    .outputs f
    
    .names a b f
    1- 1
    -1 1
    
    .end
    """
    
    # Buggy version: AND instead of OR
    impl_blif = """
    .model impl
    .inputs a b
    .outputs f
    
    .names a b f
    11 1
    
    .end
    """
    
    spec = blif_parser.parse_string(spec_blif)
    impl = blif_parser.parse_string(impl_blif)
    
    print("Spec circuit:")
    spec.print_stats()
    print("\nImpl circuit (buggy):")
    impl.print_stats()
    
    # Encode with gate 'f' parameterized
    encoding = encode(impl, spec, gates_to_fix={'f'})
    
    print(f"\nParameters to synthesize: {len(encoding['params'])}")
    print(f"Primary inputs: {len(encoding['inputs'])}")
    print(f"Gates to fix: {list(encoding['param_info'].keys())}")
    
    # Quick test: can Z3 find the OR function?
    s = Solver()
    s.add(encoding['behavior'])
    s.add(encoding['correctness'])
    
    if s.check() == sat:
        print("\nSolution found!")
        model = s.model()
        fixes = extract_solution(model, encoding['param_info'])
        for gate, info in fixes.items():
            print(f"  Gate '{gate}': {info['gate_type']} (params: {info['params']})")
    else:
        print("\nNo solution (this shouldn't happen for this example)")
