"""
Circuit Rectifier - Main Entry Point

Uses CEGIS to find fixes for buggy circuits.

Usage:
    python main.py --impl buggy.blif --spec golden.blif --fix gate1,gate2
    python main.py --impl buggy.blif --spec golden.blif --fix-all
"""

import argparse
import sys
import time

import blif_parser
import encoder
import cegis


def main():
    parser = argparse.ArgumentParser(
        description='Rectify buggy circuits using CEGIS-based synthesis',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Fix specific gates
  python main.py --impl buggy.blif --spec golden.blif --fix n1,n2

  # Try to fix all gates (expensive for large circuits)
  python main.py --impl buggy.blif --spec golden.blif --fix-all

  # Verbose output
  python main.py --impl buggy.blif --spec golden.blif --fix n1 -v
        """
    )
    
    parser.add_argument('--impl', required=True,
                        help='Path to buggy implementation BLIF file')
    parser.add_argument('--spec', required=True,
                        help='Path to correct specification BLIF file')
    parser.add_argument('--fix', type=str,
                        help='Comma-separated list of gate names to fix')
    parser.add_argument('--fix-all', action='store_true',
                        help='Try to fix all gates (can be slow)')
    parser.add_argument('--max-iter', type=int, default=10000,
                        help='Maximum CEGIS iterations (default: 10000)')
    parser.add_argument('-v', '--verbose', action='store_true',
                        help='Print detailed progress')
    parser.add_argument('--stats', action='store_true',
                        help='Print circuit statistics')
    
    args = parser.parse_args()
    
    # Validate arguments
    if not args.fix and not args.fix_all:
        parser.error('Must specify either --fix or --fix-all')
    
    # Parse circuits
    try:
        impl_circuit = blif_parser.parse(args.impl)
        spec_circuit = blif_parser.parse(args.spec)
    except FileNotFoundError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
    except blif_parser.BlifParseError as e:
        print(f"Parse error: {e}", file=sys.stderr)
        sys.exit(1)
    

    
    # Print circuit stats if requested
    if args.stats:
        print("Implementation circuit:")
        impl_circuit.print_stats()
        print("\nSpecification circuit:")
        spec_circuit.print_stats()
        print()
    
    # Determine gates to fix
    if args.fix_all:
        gates_to_fix = {gate.name for gate in impl_circuit.gates}
    else:
        gates_to_fix = set(args.fix.split(','))
        
        # Validate gate names
        impl_gate_names = {gate.name for gate in impl_circuit.gates}
        invalid = gates_to_fix - impl_gate_names
        if invalid:
            print(f"Error: Unknown gates: {invalid}", file=sys.stderr)
            print(f"Available gates: {impl_gate_names}", file=sys.stderr)
            sys.exit(1)
    
    # Check for unsupported gates (>2 inputs)
    for gate_name in gates_to_fix:
        gate = impl_circuit.get_gate(gate_name)
        if gate and gate.num_inputs() > 2:
            print(f"Error: Gate '{gate_name}' has {gate.num_inputs()} inputs. "
                  f"Only gates with <=2 inputs are supported for parameterization.",
                  file=sys.stderr)
            sys.exit(1)
    
    print(f"Rectifying circuit: {impl_circuit.name}")
    print(f"  Gates to fix: {gates_to_fix}")
    print(f"  Total parameters: {sum(2 ** impl_circuit.get_gate(g).num_inputs() for g in gates_to_fix)}")
    print()
    
    # Encode circuits
    try:
        enc = encoder.encode(impl_circuit, spec_circuit, gates_to_fix)
    except ValueError as e:
        print(f"Encoding error: {e}", file=sys.stderr)
        sys.exit(1)
    
    # Run CEGIS
    print("Running CEGIS...")
    start_time = time.time()
    
    result = cegis.run(
        encoding=enc,
        max_iterations=args.max_iter,
        verbose=args.verbose
    )
    
    elapsed = time.time() - start_time
    
    # Print results
    print()
    print("=" * 50)
    print("RESULTS")
    print("=" * 50)
    
    if result['success']:
        print(f"Status: SUCCESS")
        print(f"Iterations (test patterns): {result['iterations']}")
        print(f"Time: {elapsed:.3f}s")
        print()
        print("Fixes found:")
        
        fixes = encoder.extract_solution(result['model'], enc['param_info'])
        for gate_name, info in fixes.items():
            orig_gate = impl_circuit.get_gate(gate_name)
            orig_type = orig_gate.truth_table.identify_gate_type()
            new_type = info['gate_type']
            
            if orig_type != new_type:
                print(f"  {gate_name}: {orig_type} -> {new_type}")
            else:
                print(f"  {gate_name}: {orig_type} (unchanged)")
    else:
        print(f"Status: FAILED")
        print(f"Iterations: {result['iterations']}")
        print(f"Reason: {result['reason']}")
        print(f"Time: {elapsed:.3f}s")
        sys.exit(1)


if __name__ == "__main__":
    main()

