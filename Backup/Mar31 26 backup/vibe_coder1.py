import requests
import json
import time
import os
import re

# --- CONFIGURATION ---
MODEL = "qwen2.5-coder:7b"
OLLAMA_API = "http://localhost:11434/api/generate"
OUTPUT_FILE = os.path.expanduser("~/Desktop/minecraft_clone.html")

# The roadmap for a 3D Voxel World
ROADMAP = [
    "Write a single-file HTML5 page using Three.js (from CDN). Create a 3D scene with a basic 'grass' ground plane, a sky color, and a First Person camera. The user should be able to look around with the mouse (PointerLockControls). Output ONLY valid HTML.",

    "Update the code to add a player 'body' with gravity and basic WASD movement. The player should collide with the ground plane and not fall through. Output the entire updated HTML file.",

    "Update the code to replace the flat ground with a grid of 3D cubes (voxels). Generate a 10x10 area of grass blocks. Ensure performance is stable by using basic BoxGeometry. Output the entire updated HTML file.",

    "Update the code to add 'Mining and Placing'. When the user Left-Clicks, remove the block they are looking at. When they Right-Click, place a new block on the face they are looking at. Output the entire updated HTML file.",

    "Update the code to add basic 'World Generation'. Instead of a flat grid, use a simple noise function (or random heights) to create hills and valleys in a 16x16 area. Output the entire updated HTML file.",

    "Update the code to add different block types. Press keys 1, 2, or 3 to switch between Grass, Dirt, and Stone (different colors). The placed block should match the selected type. Output the entire updated HTML file.",

    "Update the code to add a 'Hotbar' UI at the bottom of the screen showing the selected block and a crosshair in the center of the screen. Output the entire updated HTML file.",

    "Final Polish: Add a 'Sun' (DirectionalLight) that casts shadows and a simple cloud system (white flat boxes high in the sky) that slowly move. Output the entire updated HTML file."
]

def call_ollama(prompt):
    print("\n[>>] Sending instructions to local AI engine...")
    payload = {
        "model": MODEL,
        "prompt": prompt,
        "stream": False,
        "options": {
            "num_ctx": 16384, # Increased for 3D boilerplate
            "temperature": 0.2 # Lower temp for more stable code structure
        }
    }
    
    start_time = time.time()
    try:
        response = requests.post(OLLAMA_API, json=payload)
        response.raise_for_status()
        end_time = time.time()
        print(f"[OK] Generation complete in {round(end_time - start_time, 1)} seconds.")
        return response.json().get("response", "")
    except Exception as e:
        print(f"[ERROR] Failed to connect to Ollama: {e}")
        return None

def extract_code(text):
    """Robust extraction for HTML/Markdown blocks."""
    pattern = r"```html\s?(.*?)\s?```"
    match = re.search(pattern, text, re.DOTALL | re.IGNORECASE)
    if match:
        return match.group(1).strip()
    
    # Fallback to generic code block
    secondary_pattern = r"```\s?(.*?)\s?```"
    match = re.search(secondary_pattern, text, re.DOTALL | re.IGNORECASE)
    if match:
        return match.group(1).strip()
    return text.strip()

def main():
    print(f"=== INITIATING VOXEL ENGINE BUILD on {MODEL} ===")
    print(f"Target file: {OUTPUT_FILE}")
    
    current_code = ""
    
    for i, instruction in enumerate(ROADMAP):
        print(f"\n--- ITERATION {i+1} / {len(ROADMAP)} ---")
        goal_text = instruction.split('add ')[-1].split('.')[0] if 'add ' in instruction else 'Initialize 3D Scene'
        print(f"Goal: {goal_text}")
        
        if current_code:
            full_prompt = f"{instruction}\n\nExisting Code:\n```html\n{current_code}\n```\n\nReturn ONLY the full updated HTML."
        else:
            full_prompt = instruction
            
        raw_response = call_ollama(full_prompt)
        
        if raw_response:
            clean_code = extract_code(raw_response)
            with open(OUTPUT_FILE, "w") as f:
                f.write(clean_code)
            current_code = clean_code
            print(f"[+] Iteration {i+1} saved. Refresh browser to view.")
        
        print("Cooling down (20s) to manage thermal load...")
        time.sleep(20)
        
    print("\n=== VOXEL WORLD COMPLETE ===")

if __name__ == "__main__":
    main()