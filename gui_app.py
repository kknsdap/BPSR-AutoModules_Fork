# gui_app.py

import tkinter
from tkinter import simpledialog
import customtkinter as ctk
from customtkinter import CTkFont
import threading
from typing import Optional, Dict, List, Any
import queue
import logging
import re
import sys
import os
import json
import webbrowser
from module_optimizer import ModuleOptimizer
from module_types import ModuleCategory
from PIL import Image
import sys

try:
    from network_interface_util import get_network_interfaces
except Exception as e:
    logging.warning(f"Could not import network_interface_util: {e}. Falling back to dummy interfaces for UI testing.")
    def get_network_interfaces():
        # Return a minimal list of interfaces for UI tests when psutil or related packages are missing
        return [
            {"name": "lo0", "description": "Loopback (dummy)"},
            {"name": "eth0", "description": "Ethernet (dummy)"}
        ]
try:
    from star_resonance_monitor_core import StarResonanceMonitor
except Exception as e:
    logging.warning(f"Could not import StarResonanceMonitor: {e}. Monitor features disabled (no dummy data will be generated).")

    class StarResonanceMonitor:
        """Lightweight stub used when the real StarResonanceMonitor cannot be imported.

        This stub does not generate dummy data. It provides the minimal API the UI expects
        so the application can run without automatic data generation.
        """
        def __init__(self, *args, on_data_captured_callback=None, progress_callback=None, on_results_callback=None, **kwargs):
            self.on_data_captured_callback = on_data_captured_callback
            self.progress_callback = progress_callback
            self.on_results_callback = on_results_callback
            self._stopped = True
            self._has_data = False
            self.captured_modules = []

        def start_monitoring(self):
            # No automatic capture when the real monitor is unavailable.
            if self.progress_callback:
                self.progress_callback("Monitor unavailable: install required dependencies to enable capture.")

        def stop_monitoring(self):
            self._stopped = True

        def rescreen_modules(self, *args, **kwargs):
            if self.progress_callback:
                self.progress_callback("Monitor unavailable: cannot rescreen without the real monitor.")

        def has_captured_data(self):
            return False
from logging_config import setup_logging


def resource_path(rel_path: str) -> str:
    """Return an absolute path to a resource, working for dev and for PyInstaller bundle.

    Use `getattr(sys, '_MEIPASS', ...)` to find the temporary bundle folder when running
    from a PyInstaller onefile/onedir executable.
    """
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, rel_path)

# --- Log Queue Handler (unchanged) ---
class QueueHandler(logging.Handler):
    def __init__(self, log_queue):
        super().__init__()
        self.log_queue = log_queue

    def emit(self, record):
        self.log_queue.put(self.format(record))

# --- Standard Output Stream Redirection to Queue (unchanged) ---
class StreamToQueue:
    def __init__(self, text_queue):
        self.text_queue = text_queue

    def write(self, text):
        self.text_queue.put(text)

    def flush(self):
        pass

class App(ctk.CTk):
    def __init__(self):
        super().__init__()

        # --- TEMA ---
        self.THEME = {
            "color": {
                "background_main": "#202124",      # Fondo principal (muy oscuro)
                "background_secondary": "#303134", # Paneles, botones inactivos
                "text_primary": "#E8EAED",         # Texto principal (blanco roto)
                "text_secondary": "#9AA0A6",       # Texto de placeholder o secundario
                "border": "#5F6368",               # Bordes sutiles
                "button_active_bg": "#E8EAED",     # Fondo de botón activo (el color del texto)
                "button_active_text": "#202124"    # Texto de botón activo (el color del fondo)
            },
            "font": {
                "main": ("Segoe UI", 12),
                "title": ("Segoe UI", 18, "bold"),
                "subtitle": ("Segoe UI", 14, "bold"),
                "small": ("Segoe UI", 10)
            }
        }
        # --- FIN DE TEMA ---
        
        self.title("BPSR Module Optimizer by: MrSnake")
        # Aplicar color de fondo a la ventana principal
        self.configure(fg_color=self.THEME["color"]["background_main"])
        try:
            self.iconbitmap(resource_path("icon.ico"))
        except Exception:
            pass
        self.attributes("-topmost", True)
        # Slightly smaller, more compact window
        self.geometry("1000x820")
        self.protocol("WM_DELETE_WINDOW", self.on_closing)

        # --- Load Icon Font ---
        self.fa_font = self.load_font_awesome()

        self.monitor_thread: Optional[threading.Thread] = None
        self.monitor_instance: Optional[StarResonanceMonitor] = None
        self.module_optimizer = ModuleOptimizer()
        self.interfaces = get_network_interfaces()
        self.interface_map = {f"{i}: {iface.get('description', iface['name'])}": iface['name'] 
                              for i, iface in enumerate(self.interfaces)}
        
        # --- Caching & Pagination ---
        self.all_solutions_cache: List[Any] = [] # Holds all raw solutions
        self.solutions_cache: List[Any] = [] # Holds filtered solutions for display
        self.distribution_filter = "All" # Current distribution filter
        self.current_page = 0
        self.results_per_page = 4 # Show 4 results per page
        self.captured_modules: List[Any] = [] # Holds captured modules from network
        
        # Main grid configuration for content and side console
        self.grid_columnconfigure(0, weight=1) # Column for main content
        self.grid_columnconfigure(1, weight=0) # Column for the console panel (initially no weight)
        self.grid_rowconfigure(0, weight=1) # Main row for all content

        self.main_frame = ctk.CTkFrame(self, fg_color="transparent") # Hazlo transparente para que se vea el fondo de la ventana
        self.main_frame.grid(row=0, column=0, padx=10, pady=10, sticky="nsew")
        self.main_frame.grid_columnconfigure(0, weight=1) # Columna para el frame de botones de control (izquierda)
        self.main_frame.grid_columnconfigure(1, weight=1) # Columna para el frame de instrucciones (derecha)

        # --- Language Selection ---
        self.translations = {
            "en": {
                "select_interface": "Select Network Interface:",
                "select_module_type": "Select Module Type:",
                "filter_attributes": "Filter Attributes (space separated):",
                "select_preset": "Select Preset Filter Attributes:",
                "recommended_combos": "Recommended combinations will only show the above filtered attributes, it is recommended to fill in all tolerable attributes.",
                "dynamic_instruction_1": "Before pressing the ",
                "dynamic_instruction_2": " button, move your character to a location with few players around.",
                "waiting_for_modules": "Waiting for modules to be combined",
                "change_channel_instruction": "Change channels in-game to start processing modules.",
                "refilter": "🔍 Refilter",
                "save_preset_title": "Save Preset",
                "save_preset_prompt": "Enter a name for the current attribute selection:",
                "delete_preset_title": "Delete Preset",
                "delete_preset_prompt": "Are you sure you want to delete the preset '{preset_name}'?",
                "save": "💾 Save",
            "delete": "🗑️ Delete"
        },
        "es": {
            "select_interface": "Selecciona la Interfaz de Red:",
            "select_module_type": "Selecciona el Tipo de Módulo:",
            "filter_attributes": "Filtrar Atributos (separados por coma):",
            "select_preset": "Seleccionar Atributos de Filtro Predefinidos:",
            "recommended_combos": "Las combinaciones recomendadas solo mostrarán los atributos filtrados anteriormente, se recomienda rellenar todos los atributos tolerables.",
            "dynamic_instruction_1": "Antes de presionar el botón ",
            "dynamic_instruction_2": " mueve tu personaje a un lugar con pocos jugadores a tu alrededor.",
            "waiting_for_modules": "Espera a que combine los Modulos",
            "change_channel_instruction": "Cambia de canal dentro del juego para comenzar a procesar módulos.",
            "refilter": "🔍 Refiltrar",
            "save_preset_title": "Guardar Preset",
            "save_preset_prompt": "Introduce un nombre para la selección de atributos actual:",
            "delete_preset_title": "Eliminar Preset",
            "delete_preset_prompt": "¿Estás seguro de que quieres eliminar el preset '{preset_name}'?",
            "save": "💾 Guardar",
            "delete": "🗑️ Eliminar",
            "enable_priority_ordering": "Activar Modo de Ordenamiento por Prioridad (máx. 6 atributos)",
            "select_priority_attrs": "Selecciona atributos para priorizar (máx. 6)."
        }
        }
        self.current_language = "en"

        # --- Title Frame ---
        title_frame = ctk.CTkFrame(self.main_frame, fg_color="transparent")
        title_frame.grid(row=0, column=0, pady=(5, 2), sticky="w", padx=5)

        app_icon_img = ctk.CTkImage(Image.open(resource_path("icon.png")), size=(40, 40))
        app_icon = ctk.CTkLabel(title_frame, image=app_icon_img, text="")
        app_icon.pack(side="left", padx=(0, 10))

        self.title_label = ctk.CTkLabel(title_frame, text="BPSR Module Optimizer", 
                                font=self.THEME["font"]["title"], 
                                text_color=self.THEME["color"]["text_primary"])
        self.title_label.pack(side="left")

        language_menu = ctk.CTkOptionMenu(title_frame, values=["English", "Español"], command=self.change_language)
        language_menu.pack(side="left", padx=10)
        language_menu.set("English")


        # --- Social Media Links ---
        social_frame = ctk.CTkFrame(self.main_frame, fg_color="transparent")
        social_frame.grid(row=0, column=1, pady=(5, 2), sticky="e")

        kick_img = ctk.CTkImage(Image.open(resource_path("Icons/kick.png")), size=(24, 24))
        kick_icon = ctk.CTkLabel(social_frame, image=kick_img, text="", cursor="hand2")
        kick_icon.pack(side="left", padx=2)
        kick_icon.bind("<Button-1>", lambda e: webbrowser.open_new("https://kick.com/mrsnakevt"))
        youtube_img = ctk.CTkImage(Image.open(resource_path("Icons/youtube.png")), size=(24, 24))
        youtube_icon = ctk.CTkLabel(social_frame, image=youtube_img, text="", cursor="hand2")
        youtube_icon.pack(side="left", padx=2)
        youtube_icon.bind("<Button-1>", lambda e: webbrowser.open_new("https://www.youtube.com/@MrSnake_VT"))
        x_img = ctk.CTkImage(Image.open(resource_path("Icons/x-twitter.png")), size=(24, 24))
        x_icon = ctk.CTkLabel(social_frame, image=x_img, text="", cursor="hand2")
        x_icon.pack(side="left", padx=2)
        x_icon.bind("<Button-1>", lambda e: webbrowser.open_new("https://x.com/MrSnakeVT"))

        # --- Filter Frame (initially visible) ---
        self.filters_frame = ctk.CTkFrame(self.main_frame, fg_color=self.THEME["color"]["background_secondary"], corner_radius=15)
        self.filters_frame.grid(row=1, column=0, columnspan=2, padx=5, pady=5, sticky="nsew")
        # Reconfiguración de columnas para self.filters_frame
        self.filters_frame.grid_columnconfigure(0, weight=1) # Columna para Category
        self.filters_frame.grid_columnconfigure(1, weight=1) # Columna para Category Menu
        self.filters_frame.grid_columnconfigure(2, weight=1) # Columna para Interface Label
        self.filters_frame.grid_columnconfigure(3, weight=1) # Columna para Interface Menu
        self.filters_frame.grid_columnconfigure(4, weight=1) # Nueva columna para priority_ordering_frame

        # Column 0
        self.label_category = ctk.CTkLabel(self.filters_frame, text="Select Module Type:", 
                                   font=self.THEME["font"]["main"],
                                   text_color=self.THEME["color"]["text_primary"])
        self.label_category.grid(row=0, column=0, padx=5, pady=(5, 2), sticky="w")
        self.category_menu = ctk.CTkOptionMenu(
            self.filters_frame, values=["All", "Attack", "Guard", "Support"],
            fg_color=self.THEME["color"]["background_main"], # Fondo interior
            button_color=self.THEME["color"]["background_secondary"], # Color del botón
            button_hover_color=self.THEME["color"]["border"],
            text_color=self.THEME["color"]["text_primary"],
            dropdown_fg_color=self.THEME["color"]["background_secondary"],
            dropdown_hover_color=self.THEME["color"]["border"],
            corner_radius=8
        )
        self.category_menu.grid(row=0, column=1, padx=5, pady=2, sticky="ew")
        self.category_menu.set("All")
        self.category_menu.configure(state="normal") # Ensure it\'s enabled initially

        self.label_interface = ctk.CTkLabel(self.filters_frame, text="Select Network Interface:",
                                    font=self.THEME["font"]["main"],
                                    text_color=self.THEME["color"]["text_primary"])
        self.label_interface.grid(row=0, column=2, padx=5, pady=(5, 2), sticky="w")
        self.interface_menu = ctk.CTkOptionMenu(
            self.filters_frame, values=list(self.interface_map.keys()),
            fg_color=self.THEME["color"]["background_main"],
            button_color=self.THEME["color"]["background_secondary"],
            button_hover_color=self.THEME["color"]["border"],
            text_color=self.THEME["color"]["text_primary"],
            dropdown_fg_color=self.THEME["color"]["background_secondary"],
            dropdown_hover_color=self.THEME["color"]["border"],
            corner_radius=8
        )
        self.interface_menu.grid(row=0, column=3, padx=5, pady=2, sticky="ew")

        # --- Presets Frame ---
        self.presets_frame = ctk.CTkFrame(self.filters_frame, fg_color=self.THEME["color"]["background_secondary"], corner_radius=15)
        self.presets_frame.grid(row=1, column=0, columnspan=4, padx=5, pady=(5,0), sticky="ew")
        self.presets_frame.grid_columnconfigure(0, weight=0)
        self.presets_frame.grid_columnconfigure(1, weight=1)
        self.presets_frame.grid_columnconfigure(2, weight=0)
        self.presets_frame.grid_columnconfigure(3, weight=0)

        self.label_presets = ctk.CTkLabel(self.presets_frame, text="Select Preset:",
                                   font=self.THEME["font"]["main"],
                                   text_color=self.THEME["color"]["text_primary"])
        self.label_presets.grid(row=0, column=0, padx=(5, 2), pady=2, sticky="w")

        self.presets_menu = ctk.CTkOptionMenu(
            self.presets_frame, command=self.apply_preset,
            fg_color=self.THEME["color"]["background_main"],
            button_color=self.THEME["color"]["background_secondary"],
            button_hover_color=self.THEME["color"]["border"],
            text_color=self.THEME["color"]["text_primary"],
            dropdown_fg_color=self.THEME["color"]["background_secondary"],
            dropdown_hover_color=self.THEME["color"]["border"],
            corner_radius=8
        )
        self.presets_menu.grid(row=0, column=1, padx=2, pady=2, sticky="ew")

        self.save_preset_button = ctk.CTkButton(self.presets_frame, text="", command=self.save_preset, width=80, corner_radius=15, 
                                                fg_color=self.THEME["color"]["background_secondary"], 
                                                text_color=self.THEME["color"]["text_primary"],
                                                hover_color=self.THEME["color"]["border"],
                                                border_width=0)
        self.save_preset_button.grid(row=0, column=2, padx=2, pady=2)

        self.delete_preset_button = ctk.CTkButton(self.presets_frame, text="", command=self.delete_preset, width=80, corner_radius=15, 
                                                  fg_color=self.THEME["color"]["background_secondary"], 
                                                  text_color=self.THEME["color"]["text_primary"],
                                                  hover_color=self.THEME["color"]["border"],
                                                  border_width=0)
        self.delete_preset_button.grid(row=0, column=3, padx=2, pady=2)

        # Hide legacy preset controls (search-only UI preferred)
        try:
            self.presets_frame.grid_remove()
        except Exception:
            pass

        self.attributes_buttons_frame = ctk.CTkFrame(self.filters_frame, fg_color="transparent")
        # Asegurarse de que las 5 columnas internas no se estiren
        for i in range(5): # Para 5 columnas lógicas (0 a 4)
            self.attributes_buttons_frame.grid_columnconfigure(i, weight=0)

        # Mover attributes_buttons_frame a la fila 2 para eliminar el espacio de la advertencia
        self.attributes_buttons_frame.grid(row=2, column=0, columnspan=4, padx=5, pady=5)

        # Hide legacy attribute pill buttons (we use the search panel instead)
        try:
            self.attributes_buttons_frame.grid_remove()
        except Exception:
            pass

        self.all_attributes = [
            "DMG Stack", "Agile", "Life Condense", "First Aid", "Life Wave", "Life Steal", 
            "Team Luck & Crit", "Final Protection", "Strength Boost", "Agility Boost", 
            "Intellect Boost", "Special Attack", "Elite Strike", "Healing Boost", 
            "Healing Enhance", "Cast Focus", "Attack SPD", "Crit Focus", "Luck Focus", 
            "Resistance", "Armor"
        ]
        
        self.attribute_buttons: Dict[str, ctk.CTkButton] = {}
        self.selected_attributes = set() # Attributes selected in the pill buttons (order not important here)
        self.ordered_prioritized_attrs: List[str] = [] # Attributes selected for priority ordering (order is important)
        self.update_filter_status() # Initial call to set warning status
        
        # --- Create "All" button ---
        all_button = ctk.CTkButton(
            self.attributes_buttons_frame,
            text="All",
            command=self.toggle_all_attributes,
            fg_color=self.THEME["color"]["background_secondary"], # Color inactivo
            text_color=self.THEME["color"]["text_primary"],
            hover_color=self.THEME["color"]["border"], # Un color sutil para el hover
            border_width=1, # Borde blanco
            border_color="white", # Color del borde blanco
            corner_radius=8, # ¡Muy importante para la forma de píldora!
            font=self.THEME["font"]["small"] # Reduce la fuente
        )
        all_button.grid(row=0, column=0, padx=1, pady=1)
        self.attribute_buttons["All"] = all_button

        # --- Create attribute buttons ---
        row, col = 0, 1
        for attr in self.all_attributes:
            if col > 4:  # Ajusta el número de columnas a 5
                col = 0
                row += 1
            
            button = ctk.CTkButton(
                self.attributes_buttons_frame,
                text=attr,
                command=lambda a=attr: self.toggle_attribute(a),
                fg_color=self.THEME["color"]["background_secondary"], # Color inactivo
                text_color=self.THEME["color"]["text_primary"],
                hover_color=self.THEME["color"]["border"], # Un color sutil para el hover
            border_width=1, # Borde blanco
            border_color="white", # Color del borde blanco
            corner_radius=8, # ¡Muy importante para la forma de píldora!
            font=self.THEME["font"]["small"] # Reduce la fuente
        )
            button.grid(row=row, column=col, padx=1, pady=1)
            self.attribute_buttons[attr] = button
            col += 1

        # --- Priority Ordering Controls ---
        # Reubicar este frame para que aparezca a la derecha de los botones de atributos
        self.priority_ordering_frame = ctk.CTkFrame(self.filters_frame, fg_color=self.THEME["color"]["background_secondary"], corner_radius=15)
        self.priority_ordering_frame.grid(row=2, column=4, padx=5, pady=(5,0), sticky="nsew") # Colocar en la fila 2, columna 4
        self.priority_ordering_frame.grid_columnconfigure(0, weight=1)

        self.priority_order_checkbox = ctk.CTkCheckBox(
            self.priority_ordering_frame, 
            text="Enable Priority Ordering Mode (max 6 attributes)", 
            font=self.THEME["font"]["main"],
            text_color=self.THEME["color"]["text_primary"],
            command=self.update_priority_attrs_ui
        )
        self.priority_order_checkbox.grid(row=0, column=0, padx=5, pady=2, sticky="w")

        self.priority_attrs_container = ctk.CTkFrame(self.priority_ordering_frame, fg_color="transparent")
        self.priority_attrs_container.grid(row=1, column=0, padx=2, pady=2, sticky="ew")
        self.priority_attrs_container.grid_columnconfigure(0, weight=1)
        # This container will hold the ordered list of attributes with up/down/remove buttons
        # Hide priority ordering UI - removed in simplified search-only design
        try:
            self.priority_ordering_frame.grid_remove()
        except Exception:
            pass

        # --- Search / Advanced Filter UI ---
        # Provides the user with the ability to add multiple attribute filters and choose sorting
        self.search_filters: List[Dict[str, Any]] = []  # Each filter: {attr, op, value}

        self.search_frame = ctk.CTkFrame(self.filters_frame, fg_color=self.THEME["color"]["background_secondary"], corner_radius=12)
        self.search_frame.grid(row=3, column=0, columnspan=5, padx=5, pady=(8,0), sticky="ew")
        self.search_frame.grid_columnconfigure(0, weight=1)

        # Attribute selector
        search_attr_values = ["TotalAttributes", "AbilityScore", "OptimizationScore"] + self.all_attributes
        self.search_attr_menu = ctk.CTkOptionMenu(self.search_frame, values=search_attr_values)
        self.search_attr_menu.grid(row=0, column=0, padx=6, pady=6, sticky="w")
        self.search_attr_menu.set("TotalAttributes")

        # Operator selector
        self.search_op_menu = ctk.CTkOptionMenu(self.search_frame, values=[">=", "<=", ">", "<", "=="]) 
        self.search_op_menu.grid(row=0, column=1, padx=6, pady=6, sticky="w")
        self.search_op_menu.set(">=")

        # Value entry
        self.search_value_entry = ctk.CTkEntry(self.search_frame, width=80)
        self.search_value_entry.grid(row=0, column=2, padx=6, pady=6, sticky="w")
        self.search_value_entry.insert(0, "0")

        # Add / Clear buttons
        add_btn = ctk.CTkButton(self.search_frame, text="Add Filter", width=100, command=self.add_search_filter)
        add_btn.grid(row=0, column=3, padx=6, pady=6)
        clear_btn = ctk.CTkButton(self.search_frame, text="Clear Filters", width=100, command=self.clear_search_filters)
        clear_btn.grid(row=0, column=4, padx=6, pady=6)

        # Container to show active filters
        self.filters_list_container = ctk.CTkFrame(self.search_frame, fg_color="transparent")
        self.filters_list_container.grid(row=1, column=0, columnspan=5, padx=6, pady=(0,6), sticky="ew")

        # Sorting controls
        sort_options = ["Optimization Score", "Combat Power", "Total Attributes"] + self.all_attributes
        self.sort_by_menu = ctk.CTkOptionMenu(self.search_frame, values=sort_options, command=lambda v: self.apply_filters_and_redisplay())
        self.sort_by_menu.grid(row=2, column=0, padx=6, pady=6, sticky="w")
        self.sort_by_menu.set("Optimization Score")
        self.sort_order_menu = ctk.CTkOptionMenu(self.search_frame, values=["Descending", "Ascending"], command=lambda v: self.apply_filters_and_redisplay()) 
        self.sort_order_menu.grid(row=2, column=1, padx=6, pady=6, sticky="w")
        self.sort_order_menu.set("Descending")
        
        # (Owned modules feature removed for a slimmer UI)

        # Combination size selector (3 or 4 modules)
        self.combo_size_menu = ctk.CTkOptionMenu(self.search_frame, values=["3 Modules", "4 Modules"], command=self._on_combo_size_change)
        self.combo_size_menu.grid(row=2, column=3, padx=6, pady=6, sticky="w")
        self.combo_size_menu.set("3 Modules")
        self.combo_size = 3
        # Track whether the user has explicitly chosen a combo size (defaults set programmatically)
        self.combo_size_user_selected = False
        # --- Control buttons (Start, Stop, Refilter, Compute) ---
        self.control_buttons_frame = ctk.CTkFrame(self.main_frame, fg_color="transparent")
        self.control_buttons_frame.grid(row=5, column=0, padx=5, pady=5, sticky="w")

        play_icon = ctk.CTkImage(Image.open(resource_path("Icons/play.png")), size=(16, 16))
        self.start_button = ctk.CTkButton(self.control_buttons_frame, text="Start", image=play_icon, command=self.start_monitoring,
                  corner_radius=6, height=30, width=90,
                  fg_color="#1F6AA5", border_width=0, state="disabled")
        self.start_button.pack(side="left", padx=5)

        stop_icon = ctk.CTkImage(Image.open(resource_path("Icons/stop.png")), size=(16, 16))
        self.stop_button = ctk.CTkButton(self.control_buttons_frame, text="Stop", image=stop_icon, command=self.stop_monitoring, state="disabled",
                      corner_radius=6, height=30, width=90,
                      fg_color=self.THEME["color"]["background_secondary"],
                      text_color=self.THEME["color"]["text_primary"],
                      hover_color=self.THEME["color"]["border"],
                      border_width=0)
        self.stop_button.pack(side="left", padx=5)
        
        self.rescreen_button = ctk.CTkButton(self.control_buttons_frame, text="Refilter", command=self.rescreen_results, state="disabled",
                      corner_radius=6, height=30, width=100,
                      fg_color=self.THEME["color"]["background_secondary"],
                      text_color=self.THEME["color"]["text_primary"],
                      hover_color=self.THEME["color"]["border"],
                      border_width=0)
        self.rescreen_button.pack(side="left", padx=5)

        # Compute combinations button (runs combinations from captured pool using selected combo_size)
        self.compute_button = ctk.CTkButton(self.control_buttons_frame, text="Compute", command=self.compute_combinations_from_captured, state="disabled",
                      corner_radius=6, height=30, width=100,
                      fg_color="#2E8B57",
                      text_color=self.THEME["color"]["text_primary"],
                      border_width=0)
        self.compute_button.pack(side="left", padx=5)

    def _on_combo_size_change(self, selection: str):
        try:
            self.combo_size = 3 if selection.startswith("3") else 4
        except Exception:
            self.combo_size = 4
        # Mark that the user explicitly selected a mode
        self.combo_size_user_selected = True

        # If we already have captured modules, enable Compute now that user picked size
        try:
            if self.monitor_instance and getattr(self.monitor_instance, 'captured_modules', None):
                self.compute_button.configure(state="normal")
        except Exception:
            pass

        # --- Dynamic Instructions (movido a la derecha) ---
        self.instruction_frame = ctk.CTkFrame(self.main_frame, fg_color=self.THEME["color"]["background_secondary"], corner_radius=15)
        self.instruction_frame.grid(row=5, column=1, padx=5, pady=5, sticky="e")
        
        self.instruction_icon = ctk.CTkLabel(self.instruction_frame, text="⚠️", font=("Segoe UI Emoji", 16), text_color="#FFCC00") # Yellow warning, reduced size
        self.instruction_icon.pack(side="left", padx=(5, 2), pady=2)

        # Frame for complex, multi-part instruction
        self.instruction_text_frame = ctk.CTkFrame(self.instruction_frame, fg_color="transparent")
        self.instruction_text_frame.pack(side="left", padx=(0, 5), pady=2)

        self.update_dynamic_instruction()

        # Label for simple, single-part instructions
        self.instruction_label_simple = ctk.CTkLabel(self.instruction_frame, text="", font=self.THEME["font"]["small"], text_color=self.THEME["color"]["text_primary"]) # Using THEME["font"]["small"]
        self.base_instruction_text = "" # For animation

        # --- Distribution Filter ---
        self.dist_filter_frame = ctk.CTkFrame(self.main_frame, fg_color="transparent")
        self.dist_filter_frame.grid(row=6, column=0, columnspan=2, padx=5, pady=(2, 0), sticky="ew")
        self.dist_filter_frame.grid_remove() # Hide initially

        self.label_dist_filter = ctk.CTkLabel(self.dist_filter_frame, text="Attr. Distribution:",
                                      font=self.THEME["font"]["main"],
                                      text_color=self.THEME["color"]["text_primary"])
        self.label_dist_filter.pack(side="left", padx=(5, 5))

        self.dist_filter_buttons: Dict[str, ctk.CTkButton] = {}
        filters = ["All", "Lv.5", "Lv.5/Lv.5", "Lv.5/Lv.6", "Lv.6/Lv.6"]
        for f in filters:
            btn = ctk.CTkButton(
                self.dist_filter_frame,
                text=f,
                command=lambda name=f: self.set_distribution_filter(name),
                fg_color=self.THEME["color"]["background_secondary"],
                text_color=self.THEME["color"]["text_primary"],
                hover_color=self.THEME["color"]["border"],
                border_width=0,
                corner_radius=15
            )
            btn.pack(side="left", padx=2)
        self.dist_filter_buttons[f] = btn

        # --- Console Panel ---
        self.console_frame = ctk.CTkFrame(self, width=400)
        self.console_frame.grid(row=0, column=1, rowspan=2, padx=5, pady=5, sticky="ns")
        self.console_frame.grid_remove() # Hide by default

        self.console_frame.grid_rowconfigure(0, weight=1)
        self.console_frame.grid_columnconfigure(0, weight=1)

        self.console_frame = ctk.CTkFrame(self, width=400, fg_color=self.THEME["color"]["background_secondary"], corner_radius=15)
        self.console_frame.grid(row=0, column=1, rowspan=2, padx=5, pady=5, sticky="ns")
        self.console_frame.grid_remove() # Hide by default

        self.console_frame.grid_rowconfigure(0, weight=1)
        self.console_frame.grid_columnconfigure(0, weight=1)

        self.log_textbox = ctk.CTkTextbox(self.console_frame, 
                                  fg_color=self.THEME["color"]["background_main"], # Un fondo más oscuro para el texto
                                  border_color=self.THEME["color"]["border"],
                                  border_width=1,
                                  text_color=self.THEME["color"]["text_primary"],
                                  font=self.THEME["font"]["main"])
        self.log_textbox.grid(row=0, column=0, padx=2, pady=2, sticky="nsew")

        # --- Status Bar ---
        self.status_frame = ctk.CTkFrame(self, fg_color="transparent", height=30)
        self.status_frame.grid(row=1, column=0, columnspan=2, padx=5, pady=(0, 5), sticky="ew")
        self.status_label = ctk.CTkLabel(self.status_frame, text="Status: Idle", anchor="w", text_color=self.THEME["color"]["text_secondary"], font=self.THEME["font"]["main"])
        self.status_label.pack(side="left", padx=5, pady=1)
        self.progress_bar = ctk.CTkProgressBar(self.status_frame, width=200, height=15)
        self.progress_bar.pack(side="right", padx=5, pady=1)
        self.progress_bar.set(0)
        self.progress_bar.pack_forget()  # Initially hidden

        self.log_queue = queue.Queue()
        logger_instance = logging.getLogger()
        logger_instance.setLevel(logging.INFO)
        logger_instance.addHandler(QueueHandler(self.log_queue))
        sys.stdout = StreamToQueue(self.log_queue)

        # --- New Progress Update Queue ---
        self.progress_queue = queue.Queue()
        self.results_queue = queue.Queue() # Queue for optimization results
        self.module_images = self.load_module_images() # Pre-load module images
        self.attribute_images = self.load_attribute_images() # Pre-load attribute icons

        # Now that critical UI widgets are created, enable the Start button
        try:
            if hasattr(self, 'start_button'):
                self.start_button.configure(state="normal")
        except Exception:
            pass

        # --- Module Inventory (compact read-only list) ---
        # Place inventory as a right-side sidebar; use compact cards and tighter spacing
        self.inventory_frame = ctk.CTkScrollableFrame(self, label_text="Modules",
                  fg_color=self.THEME["color"]["background_secondary"],
                  label_font=(self.THEME["font"]["subtitle"][0], 12),
                  label_text_color=self.THEME["color"]["text_primary"],
                  width=260, corner_radius=8)
        # grid on the right as a sidebar spanning main content rows
        self.inventory_frame.grid(row=0, column=1, rowspan=9, padx=(6,4), pady=6, sticky="ns")
        self.inventory_frame.grid_columnconfigure(0, weight=1)
        self.populate_inventory_list()

        # --- Results Display ---
        self.results_frame = ctk.CTkScrollableFrame(self.main_frame, label_text="Combinations",
                                            fg_color="transparent",
                                            label_font=self.THEME["font"]["subtitle"],
                                            label_text_color=self.THEME["color"]["text_primary"])
        self.results_frame.grid(row=7, column=0, columnspan=2, padx=5, pady=5, sticky="nsew")
        self.results_frame.grid_columnconfigure(0, weight=1)
        self.results_frame.grid_columnconfigure(1, weight=1)
        self.main_frame.grid_rowconfigure(7, weight=1) # Allow results frame to expand

        # --- Pagination Controls ---
        self.pagination_frame = ctk.CTkFrame(self.main_frame)
        self.pagination_frame.grid(row=8, column=0, columnspan=2, pady=(2, 0), sticky="ew")
        self.pagination_frame.grid_columnconfigure((0, 2), weight=1) # Center the label
        self.pagination_frame.grid_remove() # Hide initially

        self.prev_button = ctk.CTkButton(self.pagination_frame, text="< Previous", command=self.previous_page, state="disabled")
        self.prev_button.grid(row=0, column=0, sticky="e", padx=10)

        self.page_label = ctk.CTkLabel(self.pagination_frame, text="Page 1 / 1")
        self.page_label.grid(row=0, column=1, padx=10)

        self.next_button = ctk.CTkButton(self.pagination_frame, text="Next >", command=self.next_page, state="disabled")
        self.next_button.grid(row=0, column=2, sticky="w", padx=10)

        # --- Loading Animation ---
        self.loading_frame = ctk.CTkFrame(self.main_frame)
        self.loading_label = ctk.CTkLabel(self.loading_frame, text="Generating combinations, please wait...", font=("Arial", 18))
        self.loading_label.pack(pady=10, padx=10)
        self.loading_animation_label = ctk.CTkLabel(self.loading_frame, text="", font=("Courier", 20))
        self.loading_animation_label.pack(pady=5)
        self.animation_chars = ["|", "/", "-", "\\"]
        self.animation_index = 0
        self._animation_job = None

        # --- Instruction Animation ---
        self.instruction_animation_job = None
        self.instruction_animation_chars = ["", ".", "..", "..."]
        self.instruction_animation_index = 0

        self.presets = {}
        self.load_presets()
        self.update_presets_menu()

        self.after(100, self.poll_queues)
        self.update_dist_filter_buttons() # Set initial button state
        self.change_language("English") # Set default language

    def change_language(self, language: str):
        self.current_language = "en" if language == "English" else "es"
        lang_dict = self.translations[self.current_language]

        self.label_interface.configure(text=lang_dict["select_interface"])
        self.label_category.configure(text=lang_dict["select_module_type"])
        self.rescreen_button.configure(text=lang_dict["refilter"])
        self.label_presets.configure(text=lang_dict.get("select_preset", "Select Preset:"))
        self.save_preset_button.configure(text=lang_dict.get("save", "💾 Save"))
        self.delete_preset_button.configure(text=lang_dict.get("delete", "🗑️ Delete"))
        
        self.update_dynamic_instruction()
        # self.update_filter_warning_text() # Ya no es necesario

        # Update instruction text if it\'s currently visible
        if self.instruction_label_simple.winfo_viewable():
            if "Waiting" in self.base_instruction_text:
                 self.base_instruction_text = lang_dict["waiting_for_modules"]
            elif "Change channels" in self.base_instruction_text:
                 self.base_instruction_text = lang_dict["change_channel_instruction"]
            self.instruction_label_simple.configure(text=self.base_instruction_text)
        
        # self.update_filter_status() # Ya no es necesario, el warning frame fue eliminado


    def update_filter_warning_text(self):
        # Esta función ya no es necesaria para mostrar advertencias dinámicas.
        return "" # Siempre devuelve una cadena vacía

    def update_filter_status(self):
        # Esta función ya no tiene ninguna acción ya que el warning frame fue eliminado.
        pass

    def update_dynamic_instruction(self):
        # Clear previous widgets
        if not hasattr(self, 'instruction_text_frame'):
            return
        for widget in self.instruction_text_frame.winfo_children():
            widget.destroy()

        lang_dict = self.translations[self.current_language]
        
        ctk.CTkLabel(self.instruction_text_frame, text=lang_dict["dynamic_instruction_1"], font=self.THEME["font"]["small"]).pack(side="left")
        ctk.CTkLabel(self.instruction_text_frame, text="Start Monitoring", font=("Segoe UI", 12, "bold"), fg_color="#1F6AA5", corner_radius=5).pack(side="left", padx=2) # Reduced font size here as well
        ctk.CTkLabel(self.instruction_text_frame, text=lang_dict["dynamic_instruction_2"], font=self.THEME["font"]["small"]).pack(side="left")


    def load_font_awesome(self) -> Optional[CTkFont]:
        """Loads the Font Awesome font if available."""
        font_path = "Font Awesome 7 Free-Solid-900.otf"
        if os.path.exists(font_path):
            try:
                # Load the base font for normal text
                base_font_info = ctk.CTkFont(family="Segoe UI", size=12)
                # Create a new font that mixes the base with Font Awesome
                fa_font = CTkFont(family=base_font_info.cget("family"), size=14)
                # CustomTkinter does not officially support loading fonts by path,
                # but by registering it with Tkinter, it should be available.
                # This is a workaround.
                self.tk.call("font", "create", "FontAwesome", "-family", "FontAwesome", "-size", "14")
                
                # The button text can now use a mix of fonts.
                # For the icons, we will use the Unicode characters directly.
                # We return a font with a suitable size for the buttons.
                return CTkFont(family="Segoe UI", size=14)
            except Exception as e:
                logging.error(f"Could not load Font Awesome font: {e}")
                return None
        else:
            logging.warning(f"Font Awesome file not found at '{font_path}'. Icons will not be displayed.")
            return None

    def load_module_images(self) -> Dict[str, ctk.CTkImage]:
        """Loads all module images from the Modulos directory."""
        images = {}
        image_dir = resource_path("Modulos")
        if not os.path.isdir(image_dir):
            logging.warning(f"Image directory '{image_dir}' not found.")
            return images

        for filename in os.listdir(image_dir):
            if filename.endswith(".webp"):
                try:
                    # Match names like "Epic Attack" from "Epic Attack.webp"
                    name = os.path.splitext(filename)[0]
                    filepath = os.path.join(image_dir, filename)
                    img = Image.open(filepath).resize((48, 48), Image.Resampling.LANCZOS)
                    images[name] = ctk.CTkImage(light_image=img, dark_image=img, size=(48, 48))
                except Exception as e:
                    logging.error(f"Failed to load image {filename}: {e}")
        return images

    def populate_inventory_list(self):
        """Populate the inventory scroll frame with compact module cards.

        Each entry shows a small icon, the module name in bold and a one-line parts summary.
        """
        for w in self.inventory_frame.winfo_children():
            w.destroy()

        names = sorted(list(self.module_images.keys()))
        if not names:
            ctk.CTkLabel(self.inventory_frame, text="No module images found.", text_color=self.THEME["color"]["text_secondary"]).pack(padx=8, pady=8)
            return

        for i, name in enumerate(names):
            card = ctk.CTkFrame(self.inventory_frame, fg_color=self.THEME["color"]["background_main"], corner_radius=8)
            card.grid(row=i, column=0, sticky="ew", padx=6, pady=6)
            card.grid_columnconfigure(1, weight=1)

            img = self.module_images.get(name)
            if img:
                lbl_img = ctk.CTkLabel(card, image=img, text="")
                lbl_img.grid(row=0, column=0, rowspan=2, padx=(8,8), pady=6)

            name_lbl = ctk.CTkLabel(card, text=name, text_color=self.THEME["color"]["text_primary"], font=(self.THEME["font"]["main"][0], 11, "bold"))
            name_lbl.grid(row=0, column=1, sticky="w", pady=(6,0))

            # compact placeholder for parts (initially empty for image-only list)
            p_lbl = ctk.CTkLabel(card, text="", text_color=self.THEME["color"]["text_secondary"], font=(self.THEME["font"]["main"][0], 10))
            p_lbl.grid(row=1, column=1, sticky="w", pady=(0,6))

    def update_inventory_from_solutions(self, solutions: List[Any]):
        """Build an inventory list from actual captured modules in solutions.

        Each unique module will be shown with its parts (effect name + value) and an Owned checkbox.
        """
        # Collect unique modules by uuid if available, otherwise by name
        modules_map = {}
        for sol in solutions:
            for m in getattr(sol, 'modules', []):
                key = getattr(m, 'uuid', None) or getattr(m, 'name', None)
                if key not in modules_map:
                    modules_map[key] = m

        # Rebuild inventory UI
        for w in self.inventory_frame.winfo_children():
            w.destroy()

        if not modules_map:
            ctk.CTkLabel(self.inventory_frame, text="No captured modules.", text_color=self.THEME["color"]["text_secondary"]).pack(padx=8, pady=8)
            return

        for i, (key, module) in enumerate(sorted(modules_map.items(), key=lambda x: getattr(x[1], 'name', str(x[0])))):
            card = ctk.CTkFrame(self.inventory_frame, fg_color=self.THEME["color"]["background_main"], corner_radius=8)
            card.grid(row=i, column=0, sticky="ew", padx=6, pady=6)
            card.grid_columnconfigure(1, weight=1)

            img = self.module_images.get(getattr(module, 'name', ''))
            if img:
                lbl_img = ctk.CTkLabel(card, image=img, text="")
                lbl_img.grid(row=0, column=0, rowspan=2, padx=(8,8), pady=6)

            title = getattr(module, 'name', f"Module {i}")
            name_lbl = ctk.CTkLabel(card, text=title, text_color=self.THEME["color"]["text_primary"], font=(self.THEME["font"]["main"][0], 11, "bold"))
            name_lbl.grid(row=0, column=1, sticky="w", pady=(6,0))

            # Parts displayed compactly on one line
            parts_text = "  •  ".join(f"{p.name} +{p.value}" for p in getattr(module, 'parts', []))
            p_lbl = ctk.CTkLabel(card, text=parts_text, text_color=self.THEME["color"]["text_secondary"], font=(self.THEME["font"]["main"][0], 10))
            p_lbl.grid(row=1, column=1, sticky="w", pady=(0,6))

    def update_inventory_from_captured(self, modules: List[Any]):
        """Populate inventory UI from a captured module pool (list of module objects)."""
        modules_map = {}
        for m in modules:
            key = getattr(m, 'uuid', None) or getattr(m, 'name', None)
            if key not in modules_map:
                modules_map[key] = m

        # Rebuild inventory UI
        for w in self.inventory_frame.winfo_children():
            w.destroy()

        if not modules_map:
            ctk.CTkLabel(self.inventory_frame, text="No captured modules.", text_color=self.THEME["color"]["text_secondary"]).pack(padx=8, pady=8)
            return

        for i, (key, module) in enumerate(sorted(modules_map.items(), key=lambda x: getattr(x[1], 'name', str(x[0])))):
            card = ctk.CTkFrame(self.inventory_frame, fg_color=self.THEME["color"]["background_main"], corner_radius=8)
            card.grid(row=i, column=0, sticky="ew", padx=6, pady=6)
            card.grid_columnconfigure(1, weight=1)

            img = self.module_images.get(getattr(module, 'name', ''))
            if img:
                lbl_img = ctk.CTkLabel(card, image=img, text="")
                lbl_img.grid(row=0, column=0, rowspan=2, padx=(8,8), pady=6)

            title = getattr(module, 'name', f"Module {i}")
            name_lbl = ctk.CTkLabel(card, text=title, text_color=self.THEME["color"]["text_primary"], font=(self.THEME["font"]["main"][0], 11, "bold"))
            name_lbl.grid(row=0, column=1, sticky="w", pady=(6,0))

            parts_text = "  •  ".join(f"{p.name} +{p.value}" for p in getattr(module, 'parts', []))
            p_lbl = ctk.CTkLabel(card, text=parts_text, text_color=self.THEME["color"]["text_secondary"], font=(self.THEME["font"]["main"][0], 10))
            p_lbl.grid(row=1, column=1, sticky="w", pady=(0,6))

    # Owned toggling removed to simplify UI

    def load_attribute_images(self) -> Dict[str, ctk.CTkImage]:
        """Loads all attribute icon images from the Module-Effects directory."""
        images = {}
        image_dir = resource_path("Module-Effects")
        if not os.path.isdir(image_dir):
            logging.warning(f"Image directory '{image_dir}' not found.")
            return images

        for filename in os.listdir(image_dir):
            if filename.endswith(".webp"):
                try:
                    # Match names like "Armor" from "Armor.webp"
                    name = os.path.splitext(filename)[0]
                    filepath = os.path.join(image_dir, filename)
                    img = Image.open(filepath).resize((14, 14), Image.Resampling.LANCZOS)
                    images[name] = ctk.CTkImage(light_image=img, dark_image=img, size=(14, 14))
                except Exception as e:
                    logging.error(f"Failed to load attribute icon {filename}: {e}")
        return images

    def toggle_filters(self):
        if self.filters_frame.winfo_viewable():
            self.filters_frame.grid_remove()
        else:
            self.filters_frame.grid()

    def toggle_attribute(self, attribute_name: str):
        """Toggles the selection state of an attribute button and manages priority order list."""
        if attribute_name in self.selected_attributes:
            self.selected_attributes.remove(attribute_name)
            self.attribute_buttons[attribute_name].configure(fg_color=self.THEME["color"]["background_secondary"])
            # Remove from ordered list if present
            if attribute_name in self.ordered_prioritized_attrs:
                self.ordered_prioritized_attrs.remove(attribute_name)
        else:
            if len(self.ordered_prioritized_attrs) < 6: # Limit to 6 prioritized attributes
                self.selected_attributes.add(attribute_name)
                self.attribute_buttons[attribute_name].configure(fg_color="#1F6AA5") # Blue
                # Add to ordered list if not already there
                if attribute_name not in self.ordered_prioritized_attrs:
                    self.ordered_prioritized_attrs.append(attribute_name)
            else:
                logging.warning("Cannot add more than 6 prioritized attributes.")
                # Optionally, inform the user via a tooltip or status message
        
        # Update "All" button state
        if len(self.selected_attributes) == len(self.all_attributes):
            self.attribute_buttons["All"].configure(fg_color="#1F6AA5")
        else:
            self.attribute_buttons["All"].configure(fg_color=self.THEME["color"]["background_secondary"])
        
        self.update_filter_status() # Update warning status
        self.update_priority_attrs_ui() # Update the UI for ordered attributes

    def toggle_all_attributes(self):
        """Toggles all attributes on or off and manages priority order list."""
        if len(self.selected_attributes) == len(self.all_attributes):
            # If all are selected, deselect all
            self.selected_attributes.clear()
            self.ordered_prioritized_attrs.clear() # Clear ordered list as well
            for attr, button in self.attribute_buttons.items():
                button.configure(fg_color=self.THEME["color"]["background_secondary"])
        else:
            # If not all are selected, select all
            self.selected_attributes.update(self.all_attributes)
            for attr, button in self.attribute_buttons.items():
                if attr != "All":
                    button.configure(fg_color="#1F6AA5")
            self.attribute_buttons["All"].configure(fg_color="#1F6AA5")
            
            # If priority mode is enabled, add up to 6 attributes to the ordered list
            if self.priority_order_checkbox.get() == 1:
                self.ordered_prioritized_attrs = [attr for attr in self.all_attributes if attr in self.selected_attributes][:6]
            else:
                self.ordered_prioritized_attrs.clear() # Ensure it's clear if not in priority mode

        self.update_filter_status() # Update warning status
        self.update_priority_attrs_ui() # Update the UI for ordered attributes

    def poll_queues(self):
        # Merge processing of two queues
        # Process log queue
        while True:
            try:
                record = self.log_queue.get(block=False)
                self.log_textbox.configure(state="normal")
                self.log_textbox.insert("end", record)
                self.log_textbox.see("end")
                self.log_textbox.configure(state="disabled")

                # Check for specific log message to update instructions
                if "识别到游戏服务器" in record:
                    self.instruction_text_frame.pack_forget()
                    if not self.instruction_label_simple.winfo_viewable():
                        self.instruction_label_simple.pack(side="left", padx=(0, 5), pady=2)
                    
                    self.instruction_icon.configure(text="🔄", text_color="#1E90FF") # Blue sync icon
                    self.base_instruction_text = self.translations[self.current_language]["waiting_for_modules"]
                    self.instruction_label_simple.configure(text=self.base_instruction_text)
                    self.start_instruction_animation()
            except queue.Empty:
                break
        
        # Process progress queue
        while True:
            try:
                message = self.progress_queue.get(block=False)
                self.status_label.configure(text=f"Status: {message}")
                # Update progress bar
                if "Evaluating" in message and "combinations" in message:
                    self.progress_bar.pack(side="right", padx=5, pady=1)
                    self.progress_bar.set(0)
                elif "Evaluated" in message and "/" in message:
                    match = re.search(r'Evaluated (\d+)/(\d+) combinations', message)
                    if match:
                        current = int(match.group(1))
                        total = int(match.group(2))
                        progress = current / total
                        self.progress_bar.set(progress)
                elif "Completed!" in message:
                    self.progress_bar.pack_forget()
            except queue.Empty:
                break
        
        # Process results queue
        while True:
            try:
                results = self.results_queue.get(block=False)
                logging.debug(f"Received results from queue: type={type(results)}, length={len(results) if isinstance(results, list) else 'N/A'}")
                if results and isinstance(results, list) and len(results) > 0:
                    if hasattr(results[0], 'optimization_score'):
                        # This is optimization results (ModuleSolution list)
                        logging.debug(f"Received ModuleSolution results: {len(results)} items")
                        self.update_results_display(results)
                    else:
                        # This is captured modules (ModuleInfo list)
                        logging.debug(f"Received ModuleInfo results: {len(results)} items")
                        self.store_captured_modules(results)
            except queue.Empty:
                break
            except Exception as e:
                logging.error(f"Error processing results queue: {e}", exc_info=True)
                break
                
        self.after(100, self.poll_queues)

    def progress_callback(self, message: str):
        """Thread-safely puts a progress message into the queue."""
        self.progress_queue.put(message)

    def results_callback(self, results: List[Any]):
        """Thread-safely puts optimization results into the queue."""
        self.results_queue.put(results)

    def next_page(self):
        if self.current_page < (len(self.solutions_cache) - 1) // self.results_per_page:
            self.current_page += 1
            self.display_current_page()

    def previous_page(self):
        if self.current_page > 0:
            self.current_page -= 1
            self.display_current_page()

    def update_results_display(self, solutions: List[Any]):
        """Caches results, applies filters, and displays the first page."""
        self.stop_animation()
        self.stop_instruction_animation()
        self.loading_frame.grid_remove()
        self.results_frame.grid()
        self.pagination_frame.grid()
        self.instruction_frame.grid_remove() # Hide instructions
        # distribution filter is deprecated/hidden

        self.all_solutions_cache = solutions
        # Update inventory view with modules found in received results
        try:
            self.update_inventory_from_solutions(solutions)
        except Exception as e:
            logging.warning(f"Failed to update inventory from solutions: {e}")
        if self.all_solutions_cache:
            self.rescreen_button.configure(state="normal") # Enable rescreen button if there are solutions
        self.apply_filters_and_redisplay()

    def store_captured_modules(self, results: List[Any]):
        """Stores captured modules and enables Compute button."""
        if results and isinstance(results, list):
            self.captured_modules = results
            logging.info(f"Captured {len(self.captured_modules)} modules")
            self.compute_button.configure(state="normal")
            self.status_label.configure(text=f"Status: {len(self.captured_modules)} modules captured. Press Compute to calculate combinations.")
        else:
            logging.warning(f"Invalid results received: {results}")
            self.status_label.configure(text="Status: Failed to capture modules.")

    def display_current_page(self):
        """Clears and rebuilds the results display for the current page."""
        try:
            for widget in self.results_frame.winfo_children():
                try:
                    widget.destroy()
                except Exception as e:
                    logging.debug(f"Could not destroy widget: {e}")
        except Exception as e:
            logging.debug(f"Error clearing results frame: {e}")

        if not self.solutions_cache:
            self.pagination_frame.grid_remove()
            no_results_label = ctk.CTkLabel(self.results_frame, text="No valid combinations found.", font=("Segoe UI", 16))
            no_results_label.pack(pady=20)
            return

        total_pages = (len(self.solutions_cache) - 1) // self.results_per_page + 1
        self.page_label.configure(text=f"Page {self.current_page + 1} / {total_pages}")

        self.prev_button.configure(state="normal" if self.current_page > 0 else "disabled")
        self.next_button.configure(state="normal" if self.current_page < total_pages - 1 else "disabled")

        start_index = self.current_page * self.results_per_page
        end_index = start_index + self.results_per_page
        page_solutions = self.solutions_cache[start_index:end_index]

        rarity_colors = {
            "Rare": "#34558b",
            "Epic": "#6f42c1",
            "Legendary": "#ffc107"
        }

        for i, solution in enumerate(page_solutions):
            rank = start_index + i + 1
            row, col = divmod(i, 2)

            solution_frame = ctk.CTkFrame(self.results_frame, 
                              fg_color=self.THEME["color"]["background_secondary"], 
                              border_color=self.THEME["color"]["border"], # Borde sutil
                              border_width=1, 
                              corner_radius=15)
            solution_frame.grid(row=row, column=col, padx=5, pady=5, sticky="nsew")
            solution_frame.grid_columnconfigure(0, weight=1)

            header_frame = ctk.CTkFrame(solution_frame, fg_color="transparent")
            header_frame.grid(row=0, column=0, padx=5, pady=(2, 5), sticky="ew")
            header_frame.grid_columnconfigure(0, weight=1)
            header_frame.grid_columnconfigure(1, weight=1)

            left_header_frame = ctk.CTkFrame(header_frame, fg_color="transparent")
            left_header_frame.grid(row=0, column=0, sticky="w")

            header_label = ctk.CTkLabel(
                left_header_frame, 
                text=f"Rank {rank} (Score: {solution.optimization_score:.2f})",
                font=self.THEME["font"]["subtitle"],
                text_color=self.THEME["color"]["text_primary"]
            )
            header_label.pack(side="left")

            right_header_frame = ctk.CTkFrame(header_frame, fg_color="transparent")
            right_header_frame.grid(row=0, column=1, sticky="e")

            total_attr_value = sum(solution.attr_breakdown.values())
            
            # The combat power is stored in the \'score\' attribute of the solution.
            combat_power = getattr(solution, 'score', 'N/A')
            if isinstance(combat_power, (int, float)):
                combat_power = f"{combat_power:.0f}"

            stats_text = f"Total Attributes: {total_attr_value} | Ability Score: {combat_power}"
            stats_label = ctk.CTkLabel(
                right_header_frame,
                text=stats_text,
                font=self.THEME["font"]["small"],
                text_color=self.THEME["color"]["text_secondary"]
            )
            stats_label.pack(side="right")

            content_frame = ctk.CTkFrame(solution_frame, fg_color="transparent")
            content_frame.grid(row=1, column=0, padx=5, pady=2, sticky="ew")
            content_frame.grid_columnconfigure(0, weight=1)

            modules_container = ctk.CTkFrame(content_frame, fg_color="transparent")
            modules_container.grid(row=0, column=0, pady=2, sticky="nsew")
            
            for j, module in enumerate(solution.modules):
                modules_container.grid_columnconfigure(j, weight=1)
                rarity = module.name.split()[0]
                # Quita el color de rareza del fondo para un look más limpio, o hazlo más sutil.
                # Por ejemplo, puedes poner el color en el borde.
                rarity_colors = {
                    "Rare": "#34558b",
                    "Epic": "#6f42c1",
                    "Legendary": "#ffc107"
                }
                color = rarity_colors.get(rarity, self.THEME["color"]["border"])
                module_card = ctk.CTkFrame(modules_container,
                                   fg_color=self.THEME["color"]["background_main"], # Fondo neutro
                                   border_width=1,
                                   border_color=color, # Usa el color de rareza en el borde
                                   corner_radius=8,
                                   width=160)
                module_card.grid(row=0, column=j, padx=2, pady=2, sticky="ns")

                img_label = ctk.CTkLabel(module_card, image=self.module_images.get(module.name), text="")
                img_label.pack(pady=(2, 0), padx=2)
                
                attrs_frame = ctk.CTkFrame(module_card, fg_color="transparent")
                attrs_frame.pack(pady=(2,4), padx=4, anchor="w", fill="x")

                for part in module.parts:
                    attr_line_frame = ctk.CTkFrame(attrs_frame, fg_color="transparent")
                    attr_line_frame.pack(anchor="w")
                    
                    icon = self.attribute_images.get(part.name)
                    if icon:
                        icon_label = ctk.CTkLabel(attr_line_frame, image=icon, text="")
                        icon_label.pack(side="left", padx=(0, 2))

                    attr_text = f"{part.name} +{part.value}"
                    attrs_label = ctk.CTkLabel(attr_line_frame, text=attr_text, 
                                           font=self.THEME["font"]["small"],
                                           text_color=self.THEME["color"]["text_primary"])
                    attrs_label.pack(side="left")

            stats_frame = ctk.CTkFrame(content_frame, fg_color="transparent")
            stats_frame.grid(row=1, column=0, pady=(4,6), sticky="nsew")

            ctk.CTkLabel(stats_frame, text="Attr Distribution:", font=self.THEME["font"]["small"], text_color=self.THEME["color"]["text_secondary"]).pack(anchor="w", padx=4, pady=(2, 1))
            
            attr_dist_frame = ctk.CTkFrame(stats_frame, fg_color="transparent")
            attr_dist_frame.pack(anchor="w", padx=4, pady=1, fill="x")

            # Sort attributes by value (Lv) in descending order
            for attr_name, value in sorted(solution.attr_breakdown.items(), key=lambda item: item[1], reverse=True):
                level_str = "(Lv0)"
                if value >= 20: level_str = "(Lv.6)"
                elif value >= 16: level_str = "(Lv.5)"
                elif value >= 12: level_str = "(Lv.4)"
                elif value >= 8: level_str = "(Lv.3)"
                elif value >= 4: level_str = "(Lv.2)"
                elif value >= 1: level_str = "(Lv.1)"
                
                attr_line_frame = ctk.CTkFrame(attr_dist_frame, fg_color="transparent")
                attr_line_frame.pack(anchor="w", fill="x")

                icon = self.attribute_images.get(attr_name)
                if icon:
                    icon_label = ctk.CTkLabel(attr_line_frame, image=icon, text="")
                    icon_label.pack(side="left", padx=(0, 3))

                attr_dist_text = f"{attr_name} {level_str}: +{value}"
                ctk.CTkLabel(attr_line_frame, text=attr_dist_text, font=self.THEME["font"]["small"], justify="left", text_color=self.THEME["color"]["text_primary"]).pack(side="left")

    def set_distribution_filter(self, filter_name: str):
        """Sets the distribution filter and re-applies it to the cached results."""
        self.distribution_filter = filter_name
        self.update_dist_filter_buttons()
        logging.info(f"Distribution filter set to: {filter_name}")
        self.apply_filters_and_redisplay()

    def update_dist_filter_buttons(self):
        """Updates the appearance of distribution filter buttons."""
        # This color should ideally be from the theme, but this is a simple way
        selected_color = "#1F6AA5" # A blue color from the default theme
        default_color = ctk.ThemeManager.theme["CTkButton"]["fg_color"]
        
        for name, button in self.dist_filter_buttons.items():
            if name == self.distribution_filter:
                button.configure(fg_color=selected_color)
            else:
                button.configure(fg_color=default_color)

    # --- Search / Filter Helpers ---
    def add_search_filter(self):
        """Add a filter from the search controls to the active filter list and refresh UI."""
        attr = self.search_attr_menu.get()
        op = self.search_op_menu.get()
        val_str = self.search_value_entry.get().strip()
        try:
            val = int(val_str)
        except ValueError:
            try:
                val = float(val_str)
            except ValueError:
                logging.warning("Filter value must be numeric")
                return

        f = {"attr": attr, "op": op, "value": val}
        self.search_filters.append(f)
        self._rebuild_filters_list_ui()
        self.apply_filters_and_redisplay()

    def clear_search_filters(self):
        self.search_filters.clear()
        self._rebuild_filters_list_ui()
        self.apply_filters_and_redisplay()

    def remove_search_filter(self, index: int):
        if 0 <= index < len(self.search_filters):
            del self.search_filters[index]
            self._rebuild_filters_list_ui()
            self.apply_filters_and_redisplay()

    def _rebuild_filters_list_ui(self):
        for w in self.filters_list_container.winfo_children():
            w.destroy()
        for idx, f in enumerate(self.search_filters):
            txt = f"{f['attr']} {f['op']} {f['value']}"
            row_frame = ctk.CTkFrame(self.filters_list_container, fg_color="transparent")
            row_frame.grid(row=idx, column=0, sticky="ew", pady=2)
            row_frame.grid_columnconfigure(0, weight=1)
            lbl = ctk.CTkLabel(row_frame, text=txt, text_color=self.THEME["color"]["text_primary"])
            lbl.grid(row=0, column=0, sticky="w")
            rem = ctk.CTkButton(row_frame, text="Remove", width=70, command=lambda i=idx: self.remove_search_filter(i))
            rem.grid(row=0, column=1, padx=4)

    def _filter_match(self, solution: Any, f: Dict[str, Any]) -> bool:
        # determine the value to compare based on attribute name
        attr = f["attr"]
        op = f["op"]
        target = f["value"]
        # fetch value
        if attr == "TotalAttributes":
            val = sum(solution.attr_breakdown.values())
        elif attr == "AbilityScore":
            val = getattr(solution, 'score', 0) or 0
        elif attr == "OptimizationScore":
            val = getattr(solution, 'optimization_score', 0) or 0
        else:
            val = solution.attr_breakdown.get(attr, 0)

        try:
            if op == ">=":
                return val >= target
            if op == "<=":
                return val <= target
            if op == ">":
                return val > target
            if op == "<":
                return val < target
            if op == "==":
                return val == target
        except Exception:
            return False
        return False

    def _apply_search_and_sort(self, solutions: List[Any]) -> List[Any]:
        # Ignore legacy distribution filters: operate on supplied solutions only.
        filtered = list(solutions)

        # Apply search filters (AND semantics)
        if self.search_filters:
            filtered = [s for s in filtered if all(self._filter_match(s, f) for f in self.search_filters)]
        sort_by = self.sort_by_menu.get()
        reverse = True if self.sort_order_menu.get() == "Descending" else False

        def sort_key(sol: Any):
            if sort_by == "Optimization Score":
                return getattr(sol, 'optimization_score', 0) or 0
            if sort_by == "Combat Power":
                return getattr(sol, 'score', 0) or 0
            if sort_by == "Total Attributes":
                return sum(sol.attr_breakdown.values())
            # otherwise an attribute name
            return sol.attr_breakdown.get(sort_by, 0)

        try:
            filtered.sort(key=sort_key, reverse=reverse)
        except Exception as e:
            logging.warning(f"Sorting failed: {e}")

        return filtered

    def apply_filters_and_redisplay(self):
        """Filters the all_solutions_cache based on current filters and updates the display."""
        if not self.all_solutions_cache:
            self.solutions_cache = []
            self.display_current_page() # Show "No results"
            return
        # Simplified: ignore distribution filter and show all combinations that match search/ownership
        filtered_solutions = list(self.all_solutions_cache)
        # Then apply advanced search filters and sorting
        self.solutions_cache = self._apply_search_and_sort(filtered_solutions)
        self.current_page = 0
        self.display_current_page()

    def start_animation(self):
        """Starts the text-based loading animation."""
        if self._animation_job:
            return
        self.animation_index = 0
        self._animate()

    def _animate(self):
        """Helper function to update the animation frame."""
        self.loading_animation_label.configure(text=self.animation_chars[self.animation_index])
        self.animation_index = (self.animation_index + 1) % len(self.animation_chars)
        self._animation_job = self.after(100, self._animate)

    def stop_animation(self):
        """Stops the loading animation."""
        if hasattr(self, '_animation_job') and self._animation_job:
            self.after_cancel(self._animation_job)
            self._animation_job = None

    def start_instruction_animation(self):
        """Starts the text-based instruction animation."""
        if self.instruction_animation_job:
            return
        self.instruction_animation_index = 0
        self._animate_instruction()

    def _animate_instruction(self):
        """Helper function to update the instruction animation frame."""
        dots = self.instruction_animation_chars[self.instruction_animation_index]
        self.instruction_label_simple.configure(text=f"{self.base_instruction_text}{dots}")
        self.instruction_animation_index = (self.instruction_animation_index + 1) % len(self.instruction_animation_chars)
        self.instruction_animation_job = self.after(500, self._animate_instruction)

    def stop_instruction_animation(self):
        """Stops the instruction animation."""
        if hasattr(self, 'instruction_animation_job') and self.instruction_animation_job:
            self.after_cancel(self.instruction_animation_job)
            self.instruction_animation_job = None

    def load_presets(self):
        try:
            with open("custom_presets.json", "r") as f:
                self.presets = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            self.presets = {"Manual Input / Clear": ""} # Default
            self.save_presets_to_file()

    def save_presets_to_file(self):
        with open("custom_presets.json", "w") as f:
            json.dump(self.presets, f, indent=4)

    def update_presets_menu(self):
        self.presets_menu.configure(values=list(self.presets.keys()))
        self.presets_menu.set("Manual Input / Clear")

    def update_priority_attrs_ui(self):
        """Builds or clears the UI for ordered prioritized attributes based on checkbox state."""
        # Clear existing widgets in the container
        for widget in self.priority_attrs_container.winfo_children():
            widget.destroy()

        if self.priority_order_checkbox.get() == 1:
            self.priority_attrs_container.grid() # Ensure container is visible
            
            if not self.ordered_prioritized_attrs:
                label = ctk.CTkLabel(self.priority_attrs_container, text="Select attributes to prioritize (max 6).", 
                                     font=self.THEME["font"]["small"], 
                                     text_color=self.THEME["color"]["text_secondary"])
                label.pack(pady=5)
                return

            for idx, attr_name in enumerate(self.ordered_prioritized_attrs):
                attr_row_frame = ctk.CTkFrame(self.priority_attrs_container, fg_color="transparent")
                attr_row_frame.grid(row=idx, column=0, padx=2, pady=1, sticky="ew")
                attr_row_frame.grid_columnconfigure(0, weight=1) # Attribute name takes most space

                # Attribute Name
                attr_label = ctk.CTkLabel(attr_row_frame, text=f"{idx+1}. {attr_name}", 
                                          font=self.THEME["font"]["main"], 
                                          text_color=self.THEME["color"]["text_primary"],
                                          anchor="w")
                attr_label.grid(row=0, column=0, sticky="ew", padx=(0, 5))

                # Up button
                up_button = ctk.CTkButton(attr_row_frame, text="▲", width=30, height=24,
                                          fg_color=self.THEME["color"]["background_main"],
                                          text_color=self.THEME["color"]["text_primary"],
                                          hover_color=self.THEME["color"]["border"],
                                          command=lambda a=attr_name: self.move_priority_attr(a, -1))
                up_button.grid(row=0, column=1, padx=(0, 1))
                if idx == 0: up_button.configure(state="disabled")

                # Down button
                down_button = ctk.CTkButton(attr_row_frame, text="▼", width=30, height=24,
                                            fg_color=self.THEME["color"]["background_main"],
                                            text_color=self.THEME["color"]["text_primary"],
                                            hover_color=self.THEME["color"]["border"],
                                            command=lambda a=attr_name: self.move_priority_attr(a, 1))
                down_button.grid(row=0, column=2, padx=(0, 1))
                if idx == len(self.ordered_prioritized_attrs) - 1: down_button.configure(state="disabled")

                # Remove button
                remove_button = ctk.CTkButton(attr_row_frame, text="✕", width=30, height=24,
                                              fg_color="#FF4500", # Red color for remove
                                              text_color=self.THEME["color"]["text_primary"],
                                              hover_color="#DC143C",
                                              command=lambda a=attr_name: self.remove_priority_attr(a))
                remove_button.grid(row=0, column=3)
        else:
            self.priority_attrs_container.grid_remove() # Hide container if checkbox is unchecked
            self.ordered_prioritized_attrs.clear() # Clear ordered list when disabled

    def move_priority_attr(self, attr_name: str, direction: int):
        """Moves an attribute up or down in the ordered prioritized list."""
        if attr_name not in self.ordered_prioritized_attrs:
            return

        current_idx = self.ordered_prioritized_attrs.index(attr_name)
        new_idx = current_idx + direction

        if 0 <= new_idx < len(self.ordered_prioritized_attrs):
            self.ordered_prioritized_attrs[current_idx], self.ordered_prioritized_attrs[new_idx] = \
                self.ordered_prioritized_attrs[new_idx], self.ordered_prioritized_attrs[current_idx]
            self.update_priority_attrs_ui()

    def remove_priority_attr(self, attr_name: str):
        """Removes an attribute from the ordered prioritized list."""
        if attr_name in self.ordered_prioritized_attrs:
            self.ordered_prioritized_attrs.remove(attr_name)
            self.selected_attributes.discard(attr_name) # Also deselect from pill buttons
            if attr_name in self.attribute_buttons:
                self.attribute_buttons[attr_name].configure(fg_color=self.THEME["color"]["background_secondary"])
            self.update_priority_attrs_ui()
            self.update_filter_status() # Update warning status

    def apply_preset(self, preset_name: str):
        attributes_str = self.presets.get(preset_name, "")
        preset_attributes = set()
        if attributes_str:
            # Split the string by commas and then strip whitespace from each attribute
            temp_attributes = [attr.strip() for attr in attributes_str.split(",") if attr.strip()]
            for attr in temp_attributes:
                if attr in self.all_attributes:
                    preset_attributes.add(attr)

        # Clear current selections and ordered list
        for attr in list(self.selected_attributes):
            self.toggle_attribute(attr) # This will remove from selected_attributes and ordered_prioritized_attrs

        # Select attributes from the preset, adding to ordered list in preset's string order
        # Assuming attributes_str preserves a meaningful order if it's used for priority
        if self.priority_order_checkbox.get() == 1 and attributes_str:
            # If priority mode is on, populate ordered_prioritized_attrs directly from preset string order
            self.ordered_prioritized_attrs.clear()
            for attr in temp_attributes: # Use temp_attributes which is already ordered
                if attr in self.all_attributes and attr not in self.ordered_prioritized_attrs and len(self.ordered_prioritized_attrs) < 6:
                    self.ordered_prioritized_attrs.append(attr)
                    self.selected_attributes.add(attr) # Ensure it's marked as selected
                    if attr in self.attribute_buttons:
                        self.attribute_buttons[attr].configure(fg_color="#1F6AA5")
        else:
            # Fallback to normal selection behavior if priority mode is off or no string
            for attr in preset_attributes:
                if attr not in self.selected_attributes: # Only toggle if not already selected
                    self.toggle_attribute(attr)
        
        self.update_filter_status()
        self.update_priority_attrs_ui()

    def save_preset(self):
        lang_dict = self.translations[self.current_language]
        title = lang_dict.get("save_preset_title", "Save Preset")
        prompt = lang_dict.get("save_preset_prompt", "Enter a name for the current attribute selection:")
        
        dialog = ctk.CTkInputDialog(text=prompt, title=title)
        self.attributes("-topmost", False)
        preset_name = dialog.get_input()
        self.attributes("-topmost", True)

        if preset_name and preset_name not in self.presets:
            # Join attributes with a comma and space
            current_attributes = ", ".join(sorted(list(self.selected_attributes)))
            self.presets[preset_name] = current_attributes
            self.save_presets_to_file()
            self.update_presets_menu()
            self.presets_menu.set(preset_name)

    def delete_preset(self):
        preset_name = self.presets_menu.get()
        if preset_name == "Manual Input / Clear":
            return # Cannot delete the default
        
        lang_dict = self.translations[self.current_language]
        title = lang_dict.get("delete_preset_title", "Delete Preset")
        prompt = lang_dict.get("delete_preset_prompt", "Are you sure you want to delete the preset '{preset_name}'?").format(preset_name=preset_name)

        if tkinter.messagebox.askyesno(title, prompt):
            if preset_name in self.presets:
                del self.presets[preset_name]
                self.save_presets_to_file()
                self.update_presets_menu()

    def start_monitoring(self):
        selected_interface_display = self.interface_menu.get()
        if not selected_interface_display:
            logging.error("Error: Please select a network interface first!")
            return
        
        interface_name = self.interface_map[selected_interface_display]
        category = self.category_menu.get()
        # Simplified: no attribute priority or pill-based attribute filtering — use search UI only
        attributes = []
        prioritized_attrs = []
        priority_order_mode = False

        self.log_textbox.configure(state="normal")
        self.log_textbox.delete("1.0", "end")
        self.log_textbox.insert("end", "After pressing the start button and choosing the filter, please switch channels in the game in a place with few players around you.\n\n")
        self.log_textbox.configure(state="disabled")
        self.status_label.configure(text="Status: Starting monitoring...")
        
        # Update instruction label
        self.instruction_text_frame.pack_forget()
        self.instruction_label_simple.pack(side="left", padx=(0, 5), pady=2)
        self.instruction_icon.configure(text="⚠️", text_color="#FFA500") # Orange warning
        self.base_instruction_text = self.translations[self.current_language]["change_channel_instruction"]
        self.instruction_label_simple.configure(text=self.base_instruction_text)
        self.instruction_frame.grid()

        # Clear previous results and cache
        self.solutions_cache = []
        self.current_page = 0
        for widget in self.results_frame.winfo_children():
            widget.destroy()
        self.pagination_frame.grid_remove()

        self.monitor_instance = StarResonanceMonitor(
            interface_name=interface_name,
            category=category,
            attributes=attributes,
            prioritized_attrs=prioritized_attrs,
            priority_order_mode=priority_order_mode,
            on_data_captured_callback=self.enable_rescreening,
            progress_callback=self.progress_callback,
            on_results_callback=self.results_callback # Pass results callback
        )
        # Inform monitor of desired combination size if supported
        try:
            setattr(self.monitor_instance, 'combo_size', getattr(self, 'combo_size', 4))
        except Exception:
            pass
        
        self.monitor_thread = threading.Thread(target=self.monitor_instance.start_monitoring, daemon=True)
        self.monitor_thread.start()

        if hasattr(self, 'start_button'):
            self.start_button.configure(state="disabled")
        if hasattr(self, 'stop_button'):
            self.stop_button.configure(state="normal")
        if hasattr(self, 'interface_menu'):
            self.interface_menu.configure(state="disabled")
        if hasattr(self, 'category_menu'):
            self.category_menu.configure(state="normal")
        if hasattr(self, 'rescreen_button'):
            self.rescreen_button.configure(state="disabled")
        if hasattr(self, 'status_label'):
            self.status_label.configure(text="Status: Monitoring game data...")

    def stop_monitoring(self):
        if self.monitor_instance:
            self.monitor_instance.stop_monitoring()
        if self.monitor_thread and self.monitor_thread.is_alive():
            self.monitor_thread.join(timeout=1.0)

        self.monitor_instance = None
        self.monitor_thread = None

        if hasattr(self, 'start_button'):
            self.start_button.configure(state="normal")
        if hasattr(self, 'stop_button'):
            self.stop_button.configure(state="disabled")
        if hasattr(self, 'interface_menu'):
            self.interface_menu.configure(state="normal")
        if hasattr(self, 'category_menu'):
            self.category_menu.configure(state="normal")
        if hasattr(self, 'rescreen_button'):
            self.rescreen_button.configure(state="disabled")
        if hasattr(self, 'status_label'):
            self.status_label.configure(text="Status: Idle")
        if hasattr(self, 'dist_filter_frame'):
            self.dist_filter_frame.grid_remove() # Hide distribution filter
        self.stop_instruction_animation()

        # Reset instruction label to initial state
        if hasattr(self, 'instruction_label_simple'):
            self.instruction_label_simple.pack_forget()
        if hasattr(self, 'update_dynamic_instruction'):
            self.update_dynamic_instruction() # Re-create the initial instruction in the correct language
        if hasattr(self, 'instruction_text_frame'):
            self.instruction_text_frame.pack(side="left", padx=(0, 10), pady=5)
        if hasattr(self, 'instruction_icon'):
            self.instruction_icon.configure(text="⚠️", text_color="#FFCC00") # Yellow warning
        if hasattr(self, 'instruction_frame'):
            self.instruction_frame.grid()

    def rescreen_results(self):
        """Rescreens existing data"""
        # Compute combinations from captured pool (do not re-capture)
        if not self.monitor_instance or not getattr(self.monitor_instance, 'captured_modules', None):
            logging.warning("No captured module data available for computing combinations.")
            return

        # Clear cache and show loading animation
        self.solutions_cache = []
        self.current_page = 0
        self.pagination_frame.grid_remove()
        self.results_frame.grid_remove()
        self.instruction_frame.grid_remove() # Hide instructions
        self.loading_frame.grid(row=8, column=0, columnspan=2, padx=10, pady=10, sticky="nsew")
        self.start_animation()

        # compute in background
        threading.Thread(target=self.compute_combinations_from_captured, daemon=True).start()
    
    def enable_rescreening(self):
        """Callback function to enable the "Rescreen" button

        If `modules` is provided (a list of captured module objects), update the inventory
        from that captured pool. Otherwise, just enable rescreen/compute controls.
        """
        # if a modules list was passed, update inventory (capture time)
        def _do_update(mods):
            try:
                self.update_inventory_from_captured(mods)
            except Exception as e:
                logging.warning(f"Failed to update inventory from captured pool: {e}")

        # accept optional positional arg
        try:
            import inspect
            params = inspect.getfullargspec(self.enable_rescreening)
        except Exception:
            params = None

        # Enable UI controls
        self.rescreen_button.configure(state="normal")
        self.status_label.configure(text="Status: Data captured, ready to rescreen.")

        # If monitor_instance has captured_modules, update inventory now
        try:
            if self.monitor_instance and getattr(self.monitor_instance, 'captured_modules', None):
                _do_update(self.monitor_instance.captured_modules)
        except Exception:
            pass

        # If the user already chose combo size before/after capture, enable Compute now
        # Default to enabling Compute since combo_size defaults to 3
        try:
            if self.monitor_instance and getattr(self.monitor_instance, 'captured_modules', None):
                self.compute_button.configure(state="normal")
        except Exception:
            pass

    def compute_combinations_from_captured(self):
        """Compute all combinations from captured modules."""
        if not self.captured_modules:
            logging.warning(f"No modules captured. captured_modules={self.captured_modules}")
            self.status_label.configure(text="Status: No modules captured. Please start monitoring and capture data first.")
            return
        logging.info(f"Starting computation with {len(self.captured_modules)} modules, combo_size={self.combo_size}")

        # Run optimization in background thread
        def run_optimization():
            try:
                solutions = self.module_optimizer.get_optimal_solutions(
                    self.captured_modules,
                    category=ModuleCategory.All,
                    top_n=1000,  # Large number to get many results
                    prioritized_attrs=None,
                    priority_order_mode=False,
                    all_combinations=True,
                    combo_size=self.combo_size,
                    progress_callback=self.progress_callback
                )
                # Put results in queue for main thread
                self.results_queue.put(solutions)
            except Exception as e:
                logging.error(f"Optimization failed: {e}")
                self.progress_callback("Optimization failed.")

        threading.Thread(target=run_optimization, daemon=True).start()
        
    def on_closing(self):
        self.stop_monitoring()
        self.destroy()

if __name__ == "__main__":
    import multiprocessing
    # Add multiprocessing support for packaging tools like PyInstaller
    multiprocessing.freeze_support() 
    
    setup_logging(debug_mode=True)
    ctk.set_appearance_mode("Dark")
    ctk.set_default_color_theme("dark-blue")
    app = App()
    app.mainloop()
