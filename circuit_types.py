"""Core data structures for circuit representation."""

from dataclasses import dataclass, field


@dataclass
class TruthTable:
    """
    Represents a gate's logic function using onset cubes.
    
    Onset cubes list input patterns where output = 1.
    Each cube is a string: '1' = must be true, '0' = must be false, '-' = don't care
    
    Example - OR gate:
        num_inputs: 2
        onset_cubes: ["1-", "-1"]  # output=1 if first input=1 OR second input=1
    
    Example - AND gate:
        num_inputs: 2
        onset_cubes: ["11"]  # output=1 only if both inputs=1
    """
    num_inputs: int
    onset_cubes: list[str] = field(default_factory=list)
    
    def evaluate(self, inputs: list[bool]) -> bool:
        """Evaluate the truth table for given input values."""
        for cube in self.onset_cubes:
            match = True
            for i, c in enumerate(cube):
                if c == '1' and not inputs[i]:
                    match = False
                    break
                elif c == '0' and inputs[i]:
                    match = False
                    break
                # '-' always matches
            if match:
                return True
        return False
    
    def to_binary_string(self) -> str:
        """
        Get full truth table as binary string.
        Index 0 = all inputs false, last index = all inputs true.
        
        Example - AND gate returns "0001" (only true when both inputs true)
        Example - OR gate returns "0111" (true unless both inputs false)
        """
        if self.num_inputs > 4:
            return "TOO_LARGE"
        
        result = ""
        for i in range(2 ** self.num_inputs):
            inputs = [(i >> j) & 1 == 1 for j in range(self.num_inputs - 1, -1, -1)]
            result += "1" if self.evaluate(inputs) else "0"
        return result
    
    def identify_gate_type(self) -> str:
        """Identify common gate types from truth table."""
        tt = self.to_binary_string()
        
        gate_types = {
            # 1-input
            "01": "BUF",
            "10": "NOT",
            # 2-input  
            "0001": "AND",
            "0111": "OR",
            "1110": "NAND",
            "1000": "NOR",
            "0110": "XOR",
            "1001": "XNOR",
            "0000": "CONST0",
            "1111": "CONST1",
        }
        
        return gate_types.get(tt, f"COMPLEX({tt})")


@dataclass
class Gate:
    """
    A single logic gate in the circuit.
    
    Attributes:
        name: Output net name (unique identifier for this gate)
        inputs: List of input net names
        truth_table: The gate's logic function
    """
    name: str
    inputs: list[str]
    truth_table: TruthTable
    
    def num_inputs(self) -> int:
        return len(self.inputs)


@dataclass 
class Circuit:
    """
    Complete circuit representation.
    
    Attributes:
        name: Circuit/model name
        primary_inputs: List of primary input net names
        primary_outputs: List of primary output net names  
        gates: List of all gates in the circuit
    """
    name: str
    primary_inputs: list[str]
    primary_outputs: list[str]
    gates: list[Gate]
    
    def get_gate(self, net_name: str) -> Gate | None:
        """Find gate by its output net name."""
        for gate in self.gates:
            if gate.name == net_name:
                return gate
        return None
    
    def is_primary_input(self, net_name: str) -> bool:
        """Check if a net is a primary input."""
        return net_name in self.primary_inputs
    
    def topological_sort(self) -> list[Gate]:
        """Return gates in topological order (inputs before outputs)."""
        gate_dict = {g.name: g for g in self.gates}
        in_degree = {g.name: 0 for g in self.gates}
        dependents = {g.name: [] for g in self.gates}
    
        for gate in self.gates:
            for inp in gate.inputs:
                if inp in gate_dict:
                    in_degree[gate.name] += 1
                    dependents[inp].append(gate.name)
    

        ready = [g.name for g in self.gates if in_degree[g.name] == 0]
        sorted_gates = []
    
        while ready:
            gate_name = ready.pop(0)
            sorted_gates.append(gate_dict[gate_name])
            for dep in dependents[gate_name]:
                in_degree[dep] -= 1
                if in_degree[dep] == 0:
                    ready.append(dep)
        
        
    
        if len(sorted_gates) != len(self.gates):
            remaining = [g.name for g in self.gates if in_degree[g.name] > 0]
            raise ValueError(f"Combinational loop detected: {remaining}")
    
        return sorted_gates
    
    def print_stats(self):
        """Print circuit statistics."""
        print(f"Circuit: {self.name}")
        print(f"  Primary inputs:  {len(self.primary_inputs)}")
        print(f"  Primary outputs: {len(self.primary_outputs)}")
        print(f"  Gates: {len(self.gates)}")
        
        # Count gate types
        type_counts = {}
        for gate in self.gates:
            gtype = gate.truth_table.identify_gate_type()
            type_counts[gtype] = type_counts.get(gtype, 0) + 1
        
        print(f"  Gate types:")
        for gtype, count in sorted(type_counts.items()):
            print(f"    {gtype}: {count}")