import requests
import json
import time
import os
import re

# --- CONFIGURATION ---
MODEL = "qwen2.5-coder:7b"
OLLAMA_API = "http://localhost:11434/api/generate"
OUTPUT_FILE = os.path.expanduser("~/Desktop/vibe_game.html")

# The roadmap of features we want the AI to iteratively add over the hour
ROADMAP = [
    "Write a complete, single-file HTML5 canvas 2D game. It should be a space shooter with a black background. The player is a green ship at the bottom that moves left and right with arrow keys. Include a game loop. Output ONLY the valid HTML code.",
    
    "Take the existing HTML game code and add the ability for the player to shoot red laser projectiles upwards when the Spacebar is pressed. Ensure lasers are removed when they leave the screen. Output the entire updated HTML file.",
    
    "Take the existing HTML game code and add basic enemy ships (blue squares) that spawn at the top of the screen and move downward. If a laser hits an enemy, destroy both the laser and the enemy. Output the entire updated HTML file.",
    
    "Take the existing HTML game code and add a Score display in the top left corner. Increase the score by 10 every time an enemy is destroyed. Also, increase the enemy spawn rate slightly as the score gets higher. Output the entire updated HTML file.",
    
    "Take the existing HTML game code and add a 'Game Over' state. If an enemy touches the player's ship or reaches the bottom of the canvas, stop the game loop and display 'GAME OVER' in massive white text in the center of the screen. Output the entire updated HTML file.",
    
    "Take the existing HTML game code and add particle effects. When an enemy is destroyed, spawn 5-10 small, fading yellow/orange squares that fly out in random directions for a brief moment to simulate an explosion. Output the entire updated HTML file.",
    
    "Take the existing HTML game code and add a moving starfield background. Draw tiny white and gray dots that slowly scroll downward behind the player and enemies to give the illusion of flying through space. Output the entire updated HTML file.",
    
    "Take the existing HTML game code and add a Boss Level. When the score reaches 200, stop spawning normal enemies and spawn one massive purple Boss ship. The boss should move left and right at the top of the screen and take 20 laser hits to destroy. Output the entire updated HTML file."
]

def call_ollama(prompt):
    print("\n[>>] Sending instructions to local AI engine...")
    payload = {
        "model": MODEL,
        "prompt": prompt,
        "stream": False,
        "options": {
            "num_ctx": 8192 # Push the context window limit
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
    """Regex to rip out just the HTML code block from the LLM's chatty response."""
    # Define the pattern to look for content between ```html and ```
    pattern = r"```html\s?(.*?)\s?```"
    
    match = re.search(pattern, text, re.DOTALL | re.IGNORECASE)
    if match:
        return match.group(1).strip()
    
    # If ```html wasn't used, try a generic code block ```
    secondary_pattern = r"```\s?(.*?)\s?```"
    match = re.search(secondary_pattern, text, re.DOTALL | re.IGNORECASE)
    if match:
        return match.group(1).strip()
        
    return text.strip() # Fallback if no code blocks are used at all
    
def main():
    print(f"=== INITIATING AUTONOMOUS VIBE CODER on {MODEL} ===")
    print(f"Target file: {OUTPUT_FILE}")
    print("Warning: Thermal load will increase significantly as context window grows.\n")
    
    current_code = ""
    
    for i, instruction in enumerate(ROADMAP):
        print(f"\n--- ITERATION {i+1} / {len(ROADMAP)} ---")
        
        # Format the display output to look cleaner
        goal_text = instruction.split('add ')[-1].split('.')[0] if 'add ' in instruction else 'Create Base Game'
        print(f"Goal: {goal_text}")
        
        # If we have existing code, feed it back to the model
        if current_code:
            full_prompt = f"{instruction}\n\nHere is the current code to update:\n```html\n{current_code}\n```\n\nReturn ONLY the fully updated, runnable HTML file."
        else:
            full_prompt = instruction
            
        raw_response = call_ollama(full_prompt)
        
        if raw_response:
            clean_code = extract_code(raw_response)
            
            # Save the evolution
            with open(OUTPUT_FILE, "w") as f:
                f.write(clean_code)
                
            current_code = clean_code
            print(f"[+] File overwritten with Iteration {i+1}. Open {OUTPUT_FILE} in Chrome to play.")
        
        # Let the GPU cool off for 15 seconds before the next massive generation
        print("Cooling down for 15 seconds...")
        time.sleep(15)
        
    print("\n=== VIBE CODING COMPLETE ===")

if __name__ == "__main__":
    main()