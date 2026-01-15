# star_resonance_monitor_core.py

import logging
import time
import threading # Import threading
from typing import Dict, List, Any, Optional, Callable

from logging_config import get_logger
from module_parser import ModuleParser
from module_optimizer import ModuleOptimizer, ModuleCategory
from packet_capture import PacketCapture

logger = get_logger(__name__)

class StarResonanceMonitor:
    """Star Resonance Monitor"""

    def __init__(self, interface_name: str, category: str = "攻击", attributes: List[str] = None,
                 prioritized_attrs: Optional[List[str]] = None, priority_order_mode: bool = False,
                 on_data_captured_callback: Optional[Callable] = None,
                 progress_callback: Optional[Callable[[str], None]] = None,
                 on_results_callback: Optional[Callable[[List[Any]], None]] = None): # Add results callback
        self.interface_name = interface_name
        self.initial_category = category
        self.initial_attributes = attributes or []
        self.initial_prioritized_attrs = prioritized_attrs or []
        self.initial_priority_order_mode = priority_order_mode
        self.on_data_captured_callback = on_data_captured_callback
        self.progress_callback = progress_callback
        self.on_results_callback = on_results_callback # Save results callback
        
        self.is_running = False
        self.captured_modules: Optional[List[Any]] = None

        self.packet_capture = PacketCapture(self.interface_name)
        self.module_parser = ModuleParser()
        self.module_optimizer = ModuleOptimizer()

    def start_monitoring(self):
        self.is_running = True
        print(f"Tipo de Módulo Inicial: {self.initial_category}\n")
        if self.initial_attributes:
            print(f"Filtro de Atributos Inicial: {', '.join(self.initial_attributes)}\n")
        else:
            print("Filtro de Atributos Inicial: Ninguno\n")
        print(f"Nombre de la Interfaz de Red: {self.interface_name}\n")

        self.packet_capture.start_capture(self._on_sync_container_data)
        print("Monitoreo iniciado, por favor cambia de línea, vuelve a iniciar sesión o cambia de personaje para obtener información del módulo...\n")

    def stop_monitoring(self):
        if not self.is_running:
            return
        self.is_running = False
        self.packet_capture.stop_capture()
        print("=== Monitoring Stopped ===")

    def _on_sync_container_data(self, data: Dict[str, Any]):
        try:
            v_data = data.get('v_data')
            if v_data:
                print("Module data captured, starting parsing...")
                all_modules = self.module_parser.parse_module_info(v_data)
                
                if all_modules:
                    # Only store data and trigger callback on first capture
                    if self.captured_modules is None:
                        self.captured_modules = all_modules
                        print(f"Successfully parsed and stored {len(self.captured_modules)} modules.")
                        
                        # Pass captured modules to GUI via on_results_callback
                        if self.on_results_callback:
                            self.on_results_callback(self.captured_modules)
                        
                        # Also notify GUI to enable "Rescreen" and "Compute" buttons
                        if self.on_data_captured_callback:
                            self.on_data_captured_callback()
                    else:
                        print("Module data already captured, ignoring subsequent packets. Restart monitoring to update.")
                else:
                    print("No valid module information found in packet.")
        except Exception as e:
            logger.error(f"Failed to process data packet: {e}")

    def has_captured_data(self) -> bool:
        """Checks if module data has been captured and stored"""
        return self.captured_modules is not None

    def _run_optimization_in_background(self, category: str, attributes: List[str], 
                                         prioritized_attrs: List[str], priority_order_mode: bool):
        """
        Runs the optimization process in a separate thread to avoid blocking the UI.
        """
        if not self.has_captured_data():
            logger.error("Error: No module data available for optimization.")
            return

        print(f"\n--- Starting optimization in background with new conditions ---")
        print(f"Module Type: {category}")
        print(f"Filtered Attributes: {', '.join(attributes) if attributes else 'None'}")
        if priority_order_mode and prioritized_attrs:
            print(f"Prioritized Ordering (top 4): {', '.join(prioritized_attrs)}")
        
        category_map = {
            "All": ModuleCategory.All, "Attack": ModuleCategory.ATTACK, "Guard": ModuleCategory.GUARDIAN, "Support": ModuleCategory.SUPPORT,
            "Todos": ModuleCategory.All, "Ataque": ModuleCategory.ATTACK, "Guardia": ModuleCategory.GUARDIAN, "Soporte": ModuleCategory.SUPPORT
        }
        target_category = category_map.get(category, ModuleCategory.All)
        
        logger.info(f"Target Category: {target_category} (from input '{category}')")
        
        try:
            # Do not perform optimization here, just notify that modules are captured
            if self.on_results_callback:
                self.on_results_callback(self.captured_modules)
        except Exception as e:
            logger.error(f"Process failed: {e}")
            if self.progress_callback:
                self.progress_callback("Process failed.")

    def rescreen_modules(self, category: str, attributes: List[str], 
                         prioritized_attrs: Optional[List[str]] = None, priority_order_mode: bool = False):
        """Rescreens captured data with new filter conditions by running optimization in a separate thread."""
        if not self.has_captured_data():
            print("Error: No module data available for rescreening.")
            return

        # Start the optimization in a new thread
        optimization_thread = threading.Thread(
            target=self._run_optimization_in_background,
            args=(category, attributes, prioritized_attrs, priority_order_mode),
            daemon=True
        )
        optimization_thread.start()
