import toga
from toga.style import Pack
from toga.style.pack import COLUMN
import sys
from pathlib import Path
import json

# Add current dir to path to find verantyx modules
current_dir = Path(__file__).parent
sys.path.append(str(current_dir))

class VerantyxApp(toga.App):
    def startup(self):
        self.main_window = toga.MainWindow(title=self.formal_name)
        main_box = toga.Box(style=Pack(direction=COLUMN, padding=10))

        # Input
        main_box.add(toga.Label("Logic Query:", style=Pack(padding_bottom=5)))
        self.input_input = toga.TextInput(
            placeholder='Example: Is "[]p -> p" valid?',
            style=Pack(flex=0, padding_bottom=10)
        )
        main_box.add(self.input_input)

        # Button
        self.solve_btn = toga.Button(
            'SOLVE',
            on_press=self.do_solve,
            style=Pack(padding=10, background_color='#3b82f6', color='white')
        )
        main_box.add(self.solve_btn)

        # Status
        self.status_label = toga.Label("Initializing engine...", style=Pack(padding=5, color='gray'))
        main_box.add(self.status_label)

        # Output
        main_box.add(toga.Label("Result:", style=Pack(padding_top=10)))
        self.output_area = toga.MultilineTextInput(
            readonly=True,
            style=Pack(flex=1, font_family="monospace")
        )
        main_box.add(self.output_area)

        self.main_window.content = main_box
        self.main_window.show()

        # Load engine in background
        self.add_background_task(self.load_engine)

    async def load_engine(self, app):
        try:
            from verantyx_engine import VerantyxModel
            # Load from the bundle directory
            self.model = VerantyxModel.from_pretrained(str(Path(__file__).parent))
            self.status_label.text = "Engine Ready. (Offline Mode)"
            self.status_label.style.color = "green"
        except Exception as e:
            self.status_label.text = f"Load Error: {e}"
            self.status_label.style.color = "red"
            import traceback
            print(traceback.format_exc())

    def do_solve(self, widget):
        if not hasattr(self, 'model') or not self.model:
            self.output_area.value = "Engine not ready."
            return
        
        q = self.input_input.value
        if not q: return

        self.output_area.value = "Reasoning..."
        try:
            res = self.model.solve(q)
            # Format JSON
            text = json.dumps(res, indent=2, ensure_ascii=False)
            self.output_area.value = text
        except Exception as e:
            self.output_area.value = f"Error: {e}"

def main():
    return VerantyxApp()
