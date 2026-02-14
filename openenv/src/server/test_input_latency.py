
import time
import os
import sys
# Add parent dir to path to import wine_environment
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from wine_environment import WineEnvironment
from models import WineAction

def run_benchmark(method, iterations=100):
    print(f"\n--- Benchmarking {method} ---")
    os.environ["INPUT_METHOD"] = method
    
    try:
        env = WineEnvironment(screen_width=800, screen_height=600)
        
        # Warmup
        print("Warming up...")
        env.step(WineAction(action_type="mouse", x=0.5, y=0.5))
        
        start_time = time.time()
        
        for i in range(iterations):
            # Alternate movement to force updates
            x = 0.1 + (i % 10) * 0.05
            env.step(WineAction(action_type="mouse", x=x, y=0.5))
            
        end_time = time.time()
        duration = end_time - start_time
        avg_time = duration / iterations
        
        print(f"Total time for {iterations} steps: {duration:.4f}s")
        print(f"Average time per step: {avg_time:.4f}s")
        print(f"FPS (Control Loop): {1/avg_time:.2f}")
        
        env.close()
        return avg_time
        
    except Exception as e:
        print(f"Benchmark failed: {e}")
        return float('inf')

if __name__ == "__main__":
    print("Starting Input Latency Benchmark")
    print("Note: This measures the full Python Step -> Action -> Sleep -> Screen Capture loop.")
    
    # Test Socket (Standard)
    # Test Socket (Secondary)
    time_socket = run_benchmark("socket")
    
    # Test xdotool (Primary)
    time_xdotool = run_benchmark("xdotool")
    
    print("\n=== RESULTS ===")
    print(f"Socket:    {time_socket:.4f}s / step")
    print(f"xdotool:   {time_xdotool:.4f}s / step")
    
    if time_xdotool < time_socket:
        diff = time_socket - time_xdotool
        print(f"Winner: xdotool (faster by {diff*1000:.2f}ms per step)")
    else:
        diff = time_xdotool - time_socket
        print(f"Winner: Socket (faster by {diff*1000:.2f}ms per step)")
