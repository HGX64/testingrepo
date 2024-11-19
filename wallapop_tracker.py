from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException
from selenium.webdriver import ActionChains
import time
import sys
import json
from datetime import datetime
import argparse
import csv
import os
import traceback

class WallapopScraper:
    def __init__(self, search_term, location=None):
        self.search_term = search_term
        self.location = location if location else "madrid"
        self.base_url = "https://es.wallapop.com"
        self.search_url = self._build_search_url()
        self.headless = False
        self.driver = None
        self.wait = None
        self.results = []
        self.last_height = 0
        self.no_new_items_count = 0
        self.max_scrolls = None
        self.save_directory = "./"
        self.load_images = True
        self.price_min = None
        self.price_max = None
        self.debug = False

    def _build_search_url(self):
        """Construye la URL de búsqueda con los parámetros especificados"""
        from urllib.parse import quote
        search_term_encoded = quote(self.search_term)
        return f"{self.base_url}/app/search?keywords={search_term_encoded}&latitude=40.4168&longitude=-3.7038"

    def _setup_driver(self):
        """Configura el driver de Chrome con las opciones necesarias"""
        try:
            options = Options()
            if self.headless:
                options.add_argument('--headless')
                options.add_argument('--disable-gpu')
                options.add_argument('--window-size=1920,1080')
            options.add_argument('--no-sandbox')
            options.add_argument('--disable-dev-shm-usage')
            
            if not self.load_images:
                options.add_argument('--blink-settings=imagesEnabled=false')

            self.driver = webdriver.Chrome(options=options)
            self.wait = WebDriverWait(self.driver, 15)
            
            if self.debug:
                print("✓ Configuración del navegador:")
                print(f"  - Headless: {'Sí' if self.headless else 'No'}")
                print(f"  - Cargar imágenes: {'No' if not self.load_images else 'Sí'}")
                print(f"  - Max scrolls: {self.max_scrolls if self.max_scrolls else 'Sin límite'}")
            else:
                print("✓ Navegador configurado correctamente")

        except Exception as e:
            print(f"Error al configurar el navegador: {str(e)}")
            if self.debug:
                print("Stacktrace completo:")
                print(traceback.format_exc())
            raise

    def accept_cookies(self):
        """Acepta las cookies si aparece el diálogo"""
        try:
            cookie_button = self.wait.until(
                EC.element_to_be_clickable((By.ID, "onetrust-accept-btn-handler"))
            )
            cookie_button.click()
            if self.debug:
                print("✓ Cookies aceptadas")
        except Exception as e:
            print(f"Error al aceptar cookies: {str(e)}")

    def click_load_more(self):
        """Hace click en el botón 'Ver más productos' si está disponible"""
        try:
            # Contar productos actuales
            initial_count = len(self.driver.find_elements(By.CSS_SELECTOR, "tsl-public-item-card .ItemCard"))
            if self.debug:
                print(f"  → Productos iniciales: {initial_count}")

            # Hacer scroll al 83%
            height = self.driver.execute_script("return document.documentElement.scrollHeight")
            scroll_to = int(height * 0.83)
            self.driver.execute_script(f"window.scrollTo(0, {scroll_to});")
            time.sleep(2)  # Esperar a que se estabilice el scroll

            # Encontrar el botón
            load_more_button = self.wait.until(
                EC.presence_of_element_located((By.ID, "btn-load-more"))
            )

            # Intentar hacer click
            try:
                # Primero intentar click normal
                load_more_button.click()
            except:
                # Si falla, intentar con JavaScript
                self.driver.execute_script("arguments[0].click();", load_more_button)
            
            print("  → Click en 'Ver más productos'")
            time.sleep(3)  # Esperar a que carguen los nuevos productos

            # Verificar si se cargaron nuevos productos
            current_count = len(self.driver.find_elements(By.CSS_SELECTOR, "tsl-public-item-card .ItemCard"))
            if current_count > initial_count:
                if self.debug:
                    print(f"  → Nuevos productos cargados: {current_count - initial_count}")
                return True
            else:
                if self.debug:
                    print("  → No se cargaron nuevos productos")
                return False

        except TimeoutException:
            if self.debug:
                print("  → No se encontró el botón 'Ver más productos'")
            return False
        except Exception as e:
            if self.debug:
                print(f"  → Error al hacer click en 'Ver más productos': {str(e)}")
            return False

    def scroll_to_bottom(self, partial=False):
        """Hace scroll hacia abajo en la página
        Args:
            partial (bool): Si es True, hace scroll al 83% para encontrar el botón. Si es False, scroll completo.
        """
        try:
            # Obtener altura actual
            last_height = self.driver.execute_script("return document.documentElement.scrollHeight")
            
            # Hacer scroll
            if partial:
                # Scroll al 83% para encontrar el botón
                scroll_to = int(last_height * 0.83)
                self.driver.execute_script(f"window.scrollTo(0, {scroll_to});")
            else:
                # Scroll completo
                self.driver.execute_script("window.scrollTo(0, document.documentElement.scrollHeight);")
            
            # Esperar a que la página cargue
            time.sleep(2)
            
            # Verificar si el scroll funcionó
            new_height = self.driver.execute_script("return document.documentElement.scrollHeight")
            if new_height > last_height:
                if self.debug:
                    print(f"  → Scroll exitoso: altura anterior {last_height}, nueva altura {new_height}")
                return True
            else:
                if self.debug:
                    print("  → No hubo cambio en la altura después del scroll")
                return False
                
        except Exception as e:
            if self.debug:
                print(f"  → Error durante el scroll: {str(e)}")
            return False

    def extract_product_info(self, card):
        """Extrae la información de un producto individual"""
        try:
            # Esperar a que el elemento sea visible
            WebDriverWait(self.driver, 5).until(
                EC.visibility_of(card)
            )

            # Extraer título
            try:
                title = card.find_element(By.CSS_SELECTOR, "p.ItemCard__title").text.strip()
            except NoSuchElementException:
                title = "Título no disponible"

            # Extraer precio
            try:
                price = card.find_element(By.CSS_SELECTOR, "span.ItemCard__price").text.strip()
            except NoSuchElementException:
                price = "Precio no disponible"

            # Extraer link del producto
            try:
                link = card.find_element(By.XPATH, "./ancestor::a[1]").get_attribute("href")
            except NoSuchElementException:
                link = "Link no disponible"

            # Extraer descripción (que en este caso es el mismo título ya que no hay descripción separada)
            description = title

            # Extraer ubicación (si está disponible)
            try:
                location = card.find_element(By.CSS_SELECTOR, ".ItemCard__location").text.strip()
            except NoSuchElementException:
                location = "Ubicación no disponible"

            # Comprobar si está reservado (buscar en diferentes lugares)
            reserved = False
            try:
                # Método 1: Buscar el badge directamente
                badges = card.find_elements(By.CSS_SELECTOR, ".ItemCard__badge wallapop-badge")
                if badges:
                    for badge in badges:
                        try:
                            badge_html = badge.get_attribute('outerHTML')
                            if 'Reservado' in badge_html:
                                reserved = True
                                break
                        except:
                            continue

                # Método 2: Buscar el walla-icon si el método 1 no funcionó
                if not reserved:
                    walla_icons = card.find_elements(By.CSS_SELECTOR, "walla-icon")
                    for icon in walla_icons:
                        try:
                            next_span = icon.find_element(By.XPATH, "following-sibling::span")
                            if next_span and 'Reservado' in next_span.text:
                                reserved = True
                                break
                        except:
                            continue

                # Método 3: Buscar cualquier texto que indique reserva
                if not reserved:
                    card_text = card.text
                    if 'Reservado' in card_text:
                        reserved = True

            except Exception as e:
                reserved = False

            return {
                "title": title,
                "price": price.replace("€", "").strip(),  # Limpiamos el precio
                "description": description,
                "location": location,
                "link": link,
                "reserved": reserved,
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            }
        except Exception as e:
            print(f"Error al extraer información del producto: {str(e)}")
            return None

    def save_results(self):
        """Guarda los resultados en archivos CSV y JSON"""
        if not self.results:
            print("No hay resultados para guardar")
            return

        try:
            # Crear directorio si no existe
            os.makedirs(self.save_directory, exist_ok=True)
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            
            # Guardar en CSV
            csv_filename = f"{self.save_directory}/wallapop_{self.search_term}_{timestamp}.csv"
            with open(csv_filename, 'w', newline='', encoding='utf-8') as f:
                writer = csv.DictWriter(f, fieldnames=["title", "price", "description", "location", "link", "reserved", "timestamp"])
                writer.writeheader()
                writer.writerows(self.results)
            
            # Guardar en JSON también por si acaso
            json_filename = f"{self.save_directory}/wallapop_{self.search_term}_{timestamp}.json"
            with open(json_filename, 'w', encoding='utf-8') as f:
                json.dump(self.results, f, ensure_ascii=False, indent=2)
            
            print(f"✓ Resultados guardados en:")
            print(f"  - CSV: {csv_filename}")
            print(f"  - JSON: {json_filename}")
            
            # Mostrar resumen de resultados
            print(f"\n📊 Resumen de resultados:")
            print(f"  - Total de productos encontrados: {len(self.results)}")
            
            # Calcular precio promedio (excluyendo productos sin precio)
            prices = []
            for item in self.results:
                try:
                    price = float(item['price'].replace(',', '.').strip())
                    prices.append(price)
                except (ValueError, AttributeError):
                    continue
            
            if prices:
                avg_price = sum(prices) / len(prices)
                min_price = min(prices)
                max_price = max(prices)
                print(f"  - Precio promedio: {avg_price:.2f}€")
                print(f"  - Precio mínimo: {min_price:.2f}€")
                print(f"  - Precio máximo: {max_price:.2f}€")
            
        except Exception as e:
            print(f"Error al guardar resultados: {str(e)}")

    def scrape(self):
        """Realiza el scraping principal"""
        try:
            self._setup_driver()
            print(f"→ Buscando '{self.search_term}' en Wallapop...")
            
            self.driver.get(self.search_url)
            print("✓ Página cargada")
            
            self.accept_cookies()
            
            # Esperar un momento para que la página se estabilice
            time.sleep(2)
            
            # Realizar 3 clicks exactamente en X:45, Y:220
            print("→ Realizando clicks iniciales en (45, 220)...")
            actions = ActionChains(self.driver)
            
            for i in range(3):
                actions.move_by_offset(45, 220).click().perform()
                actions.move_by_offset(-45, -220).perform()  # Volver a la posición original
                time.sleep(0.5)
                if self.debug:
                    print(f"  ✓ Click {i+1} realizado")
            
            print("✓ Clicks completados")
            time.sleep(2)

            print("\n→ Iniciando búsqueda...")
            processed_links = set()  # Para evitar duplicados
            
            # 1. Procesar productos de la primera página
            cards = self.driver.find_elements(By.CSS_SELECTOR, "tsl-public-item-card .ItemCard")
            for card in cards:
                try:
                    product_info = self.extract_product_info(card)
                    if product_info and product_info['link'] not in processed_links:
                        # Verificar filtros de precio si están establecidos
                        price = float(product_info['price'].replace(',', '.')) if product_info['price'].replace(',', '.').replace('.', '').isdigit() else None
                        if price is not None:
                            if self.price_min is not None and price < self.price_min:
                                continue
                            if self.price_max is not None and price > self.price_max:
                                continue
                        self.results.append(product_info)
                        processed_links.add(product_info['link'])
                        if self.debug:
                            print(f"\nEncontrado: {product_info['title']} - {product_info['price']}€")
                        else:
                            print(f"\rBuscando productos: {len(self.results)}", end="", flush=True)
                except Exception as e:
                    if self.debug:
                        print(f"Error al procesar producto: {str(e)}")
                    continue

            # 2. Hacer scroll parcial y buscar el botón
            scroll_count = 0
            while scroll_count < 3:  # Intentar 3 veces máximo
                self.scroll_to_bottom(partial=True)  # Scroll parcial para encontrar el botón
                time.sleep(2)
                
                try:
                    if self.click_load_more():
                        break
                except:
                    scroll_count += 1
                    continue

            # 3. Scroll infinito y recolección de productos
            last_count = len(self.results)
            no_new_items_count = 0
            total_scrolls = 0
            
            while True:
                # Verificar si hemos alcanzado el límite de scrolls
                if self.max_scrolls is not None and total_scrolls >= self.max_scrolls:
                    print(f"\n\n→ Alcanzado el límite de {self.max_scrolls} scrolls")
                    break

                self.scroll_to_bottom(partial=False)  # Scroll completo para cargar más productos
                total_scrolls += 1
                if self.debug:
                    print(f"\nScroll #{total_scrolls}")
                time.sleep(2)
                
                cards = self.driver.find_elements(By.CSS_SELECTOR, "tsl-public-item-card .ItemCard")
                for card in cards:
                    try:
                        product_info = self.extract_product_info(card)
                        if product_info and product_info['link'] not in processed_links:
                            # Verificar filtros de precio si están establecidos
                            price = float(product_info['price'].replace(',', '.')) if product_info['price'].replace(',', '.').replace('.', '').isdigit() else None
                            if price is not None:
                                if self.price_min is not None and price < self.price_min:
                                    continue
                                if self.price_max is not None and price > self.price_max:
                                    continue
                            self.results.append(product_info)
                            processed_links.add(product_info['link'])
                            if self.debug:
                                print(f"Encontrado: {product_info['title']} - {product_info['price']}€")
                            else:
                                print(f"\rBuscando productos: {len(self.results)}", end="", flush=True)
                    except Exception as e:
                        if self.debug:
                            print(f"Error al procesar producto: {str(e)}")
                        continue
                
                current_count = len(self.results)
                if current_count > last_count:
                    last_count = current_count
                    no_new_items_count = 0
                else:
                    no_new_items_count += 1
                    if no_new_items_count >= 3:
                        print("\n\n→ No se encontraron nuevos productos después de 3 intentos")
                        break
                
                time.sleep(1)

            print(f"\n✓ Se encontraron {len(self.results)} productos")
            if self.price_min is not None or self.price_max is not None:
                print("  Filtros de precio aplicados:")
                if self.price_min is not None:
                    print(f"  - Precio mínimo: {self.price_min}€")
                if self.price_max is not None:
                    print(f"  - Precio máximo: {self.price_max}€")
            if self.max_scrolls is not None:
                print(f"  Scrolls realizados: {total_scrolls}/{self.max_scrolls}")
            
            self.save_results()

        except Exception as e:
            print(f"Error durante el scraping: {str(e)}")
            if self.debug:
                print("Stacktrace completo:")
                print(traceback.format_exc())
        finally:
            if self.driver:
                self.driver.quit()
                print("\n→ Navegador cerrado")

def main():
    parser = argparse.ArgumentParser(
        description="Wallapop Tracker - Rastrea productos en Wallapop",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Ejemplos de uso:
  python wallapop_tracker.py "iphone" --location "madrid" --headless
  python wallapop_tracker.py "ps5" --max-scrolls 5 --save-dir "./resultados"
  python wallapop_tracker.py "nintendo switch" --no-images --price-max 200
        """
    )
    
    # Argumentos obligatorios
    parser.add_argument(
        "search_term",
        help="Término de búsqueda (producto a buscar)"
    )
    
    # Argumentos opcionales
    parser.add_argument(
        "--location",
        default="madrid",
        help="Ubicación para la búsqueda (default: madrid)"
    )
    parser.add_argument(
        "--headless",
        action="store_true",
        help="Ejecutar en modo headless (sin interfaz gráfica)"
    )
    parser.add_argument(
        "--max-scrolls",
        type=int,
        default=None,
        help="Número máximo de scrolls a realizar (default: sin límite)"
    )
    parser.add_argument(
        "--save-dir",
        default="./",
        help="Directorio donde guardar los resultados (default: directorio actual)"
    )
    parser.add_argument(
        "--no-images",
        action="store_true",
        help="No cargar imágenes para acelerar el scraping"
    )
    parser.add_argument(
        "--price-min",
        type=float,
        help="Precio mínimo para filtrar resultados"
    )
    parser.add_argument(
        "--price-max",
        type=float,
        help="Precio máximo para filtrar resultados"
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Activar modo debug con más información"
    )

    args = parser.parse_args()

    # Configurar el manejador de señales para Ctrl+C
    def signal_handler(sig, frame):
        print("\n\n→ Ctrl+C detectado. Guardando resultados antes de salir...")
        if scraper and hasattr(scraper, 'results') and scraper.results:
            scraper.save_results()
        sys.exit(0)

    import signal
    signal.signal(signal.SIGINT, signal_handler)

    # Crear instancia del scraper con los argumentos
    scraper = WallapopScraper(args.search_term, args.location)
    
    # Configurar opciones adicionales
    scraper.headless = args.headless
    if args.max_scrolls:
        scraper.max_scrolls = args.max_scrolls
    if args.save_dir:
        scraper.save_directory = args.save_dir
    if args.no_images:
        scraper.load_images = False
    if args.price_min:
        scraper.price_min = args.price_min
    if args.price_max:
        scraper.price_max = args.price_max
    if args.debug:
        scraper.debug = True

    # Ejecutar el scraping
    scraper.scrape()

if __name__ == "__main__":
    main()
