"""
BLIF (Berkeley Logic Interchange Format) parser.

Parses .blif files into Circuit objects.

"""

from circuit_types import TruthTable, Gate, Circuit


class BlifParseError(Exception):
    """Raised when BLIF parsing fails."""
    def __init__(self, message: str, line_num: int = None):
        if line_num is not None:
            message = f"Line {line_num}: {message}"
        super().__init__(message)


def parse(filename: str) -> Circuit:
    """
    Parse a BLIF file and return a Circuit.
    """
    with open(filename, 'r') as f:
        content = f.read()
    return parse_string(content)


def parse_string(content: str) -> Circuit:
    """
    Parse BLIF content from a string.
    """
    lines = _preprocess(content)
    return _parse_lines(lines)


def _preprocess(content: str) -> list[tuple[int, str]]:
    """
    Preprocess BLIF content:
    - Remove comments
    - Handle line continuations (backslash)
    - Track line numbers for error messages
    
    Returns list of (line_number, line_content) tuples.
    """
    result = []
    continued_line = ""
    continued_from = None
    
    for line_num, line in enumerate(content.split('\n'), start=1):
        # Remove comments
        if '#' in line:
            line = line[:line.find('#')]
        
        # Strip whitespace
        line = line.strip()
        
        # Skip empty lines
        if not line:
            continue
        
        # Handle line continuation
        if line.endswith('\\'):
            if continued_from is None:
                continued_from = line_num
            continued_line += line[:-1] + ' '
            continue
        
        if continued_line:
            line = continued_line + line
            line_num = continued_from
            continued_line = ""
            continued_from = None
        
        result.append((line_num, line))
    
    return result


def _parse_lines(lines: list[tuple[int, str]]) -> Circuit:
    """Parse preprocessed lines into a Circuit."""
    name = "unnamed"
    primary_inputs = []
    primary_outputs = []
    gates = []
    
    current_gate = None
    
    for line_num, line in lines:
        tokens = line.split()
        
        if not tokens:
            continue
        
        cmd = tokens[0]
        
        # Directive lines start with '.'
        if cmd.startswith('.'):
            # Finish any in-progress gate
            current_gate = None
            
            if cmd == '.model':
                if len(tokens) >= 2:
                    name = tokens[1]
                    
            elif cmd == '.inputs':
                primary_inputs.extend(tokens[1:])
                
            elif cmd == '.outputs':
                primary_outputs.extend(tokens[1:])
                
            elif cmd == '.names':
                if len(tokens) < 2:
                    raise BlifParseError(".names requires at least one signal", line_num)
                
                # Last token is output, rest are inputs
                gate_inputs = tokens[1:-1]
                gate_output = tokens[-1]
                
                current_gate = Gate(
                    name=gate_output,
                    inputs=gate_inputs,
                    truth_table=TruthTable(num_inputs=len(gate_inputs))
                )
                gates.append(current_gate)
                
            elif cmd == '.end':
                break
                
            elif cmd in ('.latch', '.subckt', '.gate'):
                raise BlifParseError(f"{cmd} not supported", line_num)
                
            # Ignore unknown directives
            
        else:
            # Truth table row for current gate
            if current_gate is None:
                raise BlifParseError("Truth table row without .names", line_num)
            
            _parse_truth_table_row(tokens, current_gate, line_num)
    
    return Circuit(
        name=name,
        primary_inputs=primary_inputs,
        primary_outputs=primary_outputs,
        gates=gates
    )


def _parse_truth_table_row(tokens: list[str], gate: Gate, line_num: int):
    """
    Parse a truth table row and add to gate's onset cubes.
    
    Formats:
        "11 1"     - input pattern "11", output 1
        "1- 1"     - input pattern "1-", output 1
        "1"        - for constant output (no inputs), output 1
        "11"       - some BLIF files omit output when it's 1
    """
    if gate.truth_table.num_inputs == 0:
        # Constant gate: just "1" or "0"
        if tokens[0] == '1':
            gate.truth_table.onset_cubes.append("")
        # "0" means constant 0, onset stays empty
        return
    
    if len(tokens) == 1:
        # Output omitted, assume 1
        cube = tokens[0]
        output = '1'
    elif len(tokens) == 2:
        cube = tokens[0]
        output = tokens[1]
    else:
        raise BlifParseError(f"Invalid truth table row: {' '.join(tokens)}", line_num)
    
    # Validate cube length
    if len(cube) != gate.truth_table.num_inputs:
        raise BlifParseError(
            f"Cube '{cube}' has {len(cube)} bits but gate has {gate.truth_table.num_inputs} inputs",
            line_num
        )
    
    # Validate cube characters
    for c in cube:
        if c not in '01-':
            raise BlifParseError(f"Invalid character '{c}' in cube", line_num)
    
    # Only add to onset if output is 1
    if output == '1':
        gate.truth_table.onset_cubes.append(cube)


# Quick test when run directly
if __name__ == "__main__":
    test_blif = """
    .model test
    .inputs a b
    .outputs f
    
    # AND gate
    .names a b n1
    11 1
    
    # OR gate
    .names n1 b f
    1- 1
    -1 1
    
    .end
    """
    
    circuit = parse_string(test_blif)
    circuit.print_stats()
    
    print("\nGates:")
    for gate in circuit.gates:
        print(f"  {gate.name}: {gate.inputs} -> {gate.truth_table.identify_gate_type()}")
