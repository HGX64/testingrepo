import os
import logging
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from dotenv import load_dotenv
from wallapop_tracker import WallapopScraper
import asyncio
from datetime import datetime

# Configurar logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Cargar variables de entorno
load_dotenv()
TOKEN = os.getenv('TELEGRAM_TOKEN')

# Diccionario para almacenar las búsquedas activas
active_searches = {}

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Comando /start - Introduce el bot"""
    welcome_message = """¡Bienvenido al Bot de Wallapop! 🛍️

Comandos disponibles:
/buscar [término] - Busca productos en Wallapop
/precio_min [número] - Establece precio mínimo
/precio_max [número] - Establece precio máximo
/ubicacion [ciudad] - Establece la ubicación (default: madrid)
/ayuda - Muestra este mensaje de ayuda

Ejemplo: 
1. /ubicacion barcelona
2. /precio_min 100
3. /precio_max 500
4. /buscar iphone
"""
    await update.message.reply_text(welcome_message)

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Comando /ayuda - Muestra la ayuda"""
    await start(update, context)

async def set_min_price(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Comando /precio_min - Establece el precio mínimo"""
    user_id = update.effective_user.id
    if not context.args:
        await update.message.reply_text("Por favor, especifica un precio mínimo. Ejemplo: /precio_min 100")
        return
    
    try:
        price = float(context.args[0])
        if price < 0:
            await update.message.reply_text("El precio no puede ser negativo.")
            return
        
        if user_id not in active_searches:
            active_searches[user_id] = {}
        active_searches[user_id]['price_min'] = price
        await update.message.reply_text(f"Precio mínimo establecido a {price}€")
    except ValueError:
        await update.message.reply_text("Por favor, introduce un número válido.")

async def set_max_price(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Comando /precio_max - Establece el precio máximo"""
    user_id = update.effective_user.id
    if not context.args:
        await update.message.reply_text("Por favor, especifica un precio máximo. Ejemplo: /precio_max 500")
        return
    
    try:
        price = float(context.args[0])
        if price < 0:
            await update.message.reply_text("El precio no puede ser negativo.")
            return
        
        if user_id not in active_searches:
            active_searches[user_id] = {}
        active_searches[user_id]['price_max'] = price
        await update.message.reply_text(f"Precio máximo establecido a {price}€")
    except ValueError:
        await update.message.reply_text("Por favor, introduce un número válido.")

async def set_location(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Comando /ubicacion - Establece la ubicación"""
    user_id = update.effective_user.id
    if not context.args:
        await update.message.reply_text("Por favor, especifica una ubicación. Ejemplo: /ubicacion barcelona")
        return
    
    location = ' '.join(context.args)
    if user_id not in active_searches:
        active_searches[user_id] = {}
    active_searches[user_id]['location'] = location
    await update.message.reply_text(f"Ubicación establecida a: {location}")

async def search(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Comando /buscar - Inicia una búsqueda en Wallapop"""
    user_id = update.effective_user.id
    
    if not context.args:
        await update.message.reply_text("Por favor, especifica qué quieres buscar. Ejemplo: /buscar iphone")
        return
    
    search_term = ' '.join(context.args)
    await update.message.reply_text(f"🔍 Buscando: {search_term}...")
    
    # Obtener configuración del usuario
    user_config = active_searches.get(user_id, {})
    location = user_config.get('location', 'madrid')
    price_min = user_config.get('price_min', None)
    price_max = user_config.get('price_max', None)
    
    try:
        # Configurar el scraper
        scraper = WallapopScraper(
            search_term=search_term,
            location=location,
            headless=True,
            max_scrolls=3,
            save_directory=f"resultados_{user_id}",
            load_images=False,
            price_min=price_min,
            price_max=price_max,
            debug=False
        )
        
        # Ejecutar búsqueda en un thread separado
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, scraper.scrape)
        
        # Enviar resultados
        if scraper.results:
            # Guardar resultados en CSV y obtener el nombre del archivo
            csv_file = scraper.save_results()
            
            if csv_file and os.path.exists(csv_file):
                # Enviar archivo CSV
                await update.message.reply_document(
                    document=open(csv_file, 'rb'),
                    filename=f"wallapop_{search_term}.csv",
                    caption=f"📊 Resultados de la búsqueda: {search_term}\nEncontrados: {len(scraper.results)} productos"
                )
            else:
                await update.message.reply_text("❌ Error al generar el archivo CSV")
        else:
            await update.message.reply_text("❌ No se encontraron productos que coincidan con tu búsqueda.")
            
    except Exception as e:
        logger.error(f"Error durante la búsqueda: {str(e)}")
        await update.message.reply_text("❌ Ocurrió un error durante la búsqueda. Por favor, intenta de nuevo más tarde.")

def main():
    """Inicia el bot"""
    # Crear la aplicación
    application = Application.builder().token(TOKEN).build()

    # Agregar handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("ayuda", help_command))
    application.add_handler(CommandHandler("buscar", search))
    application.add_handler(CommandHandler("precio_min", set_min_price))
    application.add_handler(CommandHandler("precio_max", set_max_price))
    application.add_handler(CommandHandler("ubicacion", set_location))

    # Iniciar el bot
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()
