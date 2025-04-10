import flet as ft  # Framework para interfaces gráficas
from ffpyplayer.player import MediaPlayer  # Reproductor de audio
import yt_dlp  # Descarga de audio desde YouTube y otros sitios
import threading  # Para ejecutar tareas en segundo plano
import time  # Funciones relacionadas con el tiempo
import json  # Lectura y escritura de datos en formato JSON
import os  # Operaciones con el sistema de archivos

estado_pausado = False  # Variable global que indica si la canción está pausada
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Carpeta donde se guardarán las canciones
MUSIC_FOLDER = os.path.join(BASE_DIR, "music")

# Archivo JSON donde se guarda la playlist
PLAYLIST_FILE = os.path.join(BASE_DIR, "playlist.json")

# Nodo de la lista doblemente enlazada circular (una canción)
class NodoCancion:
    def __init__(self, titulo, url, miniatura, file_path=None):
        self.titulo = titulo  # Título de la canción
        self.url = url  # URL de la canción (ej. YouTube)
        self.miniatura = miniatura  # URL de la miniatura
        self.file_path = file_path  # Ruta local del archivo descargado
        self.anterior = None  # Nodo anterior en la lista
        self.siguiente = None  # Nodo siguiente en la lista

    def to_dict(self):
        return {
            "titulo": self.titulo,
            "url": self.url,
            "miniatura": self.miniatura,
            "file_path": self.file_path
        }  # Convierte el nodo en un diccionario (para guardar en JSON)

    @staticmethod
    def from_dict(data):
        return NodoCancion(
            data["titulo"],
            data["url"],
            data["miniatura"],
            data.get("file_path")
        )  # Crea un nodo desde un diccionario (cargado desde JSON)

# Lista doblemente enlazada circular 
class ListaReproduccion:
    def __init__(self):
        self.actual = None  # Nodo actual en reproducción
        self.longitud = 0  # Número de canciones en la lista

    def agregar(self, cancion):
        if not self.actual:
            self.actual = cancion  # Primera canción agregada
            cancion.siguiente = cancion.anterior = cancion  # Enlaza consigo misma
        else:
            ultima = self.actual.anterior  # Última canción de la lista
            ultima.siguiente = cancion  # Enlace hacia nueva canción
            cancion.anterior = ultima  # Enlace hacia atrás
            cancion.siguiente = self.actual  # Nueva canción apunta al inicio
            self.actual.anterior = cancion  # Enlace desde inicio hacia nueva
        self.longitud += 1  # Aumenta la longitud de la lista

    def eliminar(self, cancion):
        if self.longitud == 0:
            return  # Lista vacía, no hay nada que eliminar
        if self.longitud == 1 and self.actual == cancion:
            self.actual = None  # Elimina la única canción
        else:
            if self.actual == cancion:
                self.actual = cancion.siguiente  # Mueve el puntero actual
            cancion.anterior.siguiente = cancion.siguiente  # Ajusta enlaces
            cancion.siguiente.anterior = cancion.anterior
        self.longitud -= 1  # Disminuye la longitud

        # Elimina el archivo si existe
        if cancion.file_path and os.path.exists(cancion.file_path):
            try:
                os.remove(cancion.file_path)
            except Exception as e:
                print(f"Error al eliminar archivo: {e}")

    def siguiente(self):
        if self.actual:
            self.actual = self.actual.siguiente  # Avanza al siguiente nodo

    def anterior(self):
        if self.actual:
            self.actual = self.actual.anterior  # Retrocede al nodo anterior

    def recorrer(self):
        canciones = []
        if self.actual:
            nodo = self.actual
            for _ in range(self.longitud):  # Recorre todos los nodos
                canciones.append(nodo)
                nodo = nodo.siguiente
        return canciones  # Devuelve la lista de canciones

    def vaciar(self):
        for cancion in self.recorrer():  # Elimina archivos locales
            if cancion.file_path and os.path.exists(cancion.file_path):
                try:
                    os.remove(cancion.file_path)
                except Exception as e:
                    print(f"Error al eliminar archivo: {e}")
        self.actual = None  # Reinicia la lista
        self.longitud = 0

    def guardar(self, archivo):
        with open(archivo, "w", encoding="utf-8") as f:
            json.dump([c.to_dict() for c in self.recorrer()], f, ensure_ascii=False, indent=2)
            # Guarda la playlist como lista de diccionarios en JSON

    def cargar(self, archivo):
        if not os.path.exists(archivo):
            return  # No hay archivo para cargar
        self.vaciar()  # Limpia la lista antes de cargar
        with open(archivo, "r", encoding="utf-8") as f:
            datos = json.load(f)
            for d in datos:
                if "file_path" in d and d["file_path"] and not os.path.exists(d["file_path"]):
                    d["file_path"] = None  # Ignora archivos que ya no existen
                self.agregar(NodoCancion.from_dict(d))  # Agrega a la lista

# Variables globales
lista_reproduccion = ListaReproduccion()  # Lista de reproducción actual
player = None  # Reproductor multimedia
reproduciendo = False  # Estado de reproducción

# Crea la carpeta de música si no existe
if not os.path.exists(MUSIC_FOLDER):
    os.makedirs(MUSIC_FOLDER)

# Descarga el audio en formato MP3 desde una URL y devuelve la ruta local
def descargar_mp3(url, titulo):
    safe_title = "".join(c for c in titulo if c.isalnum() or c in " -_").rstrip()  # Limpia el título
    output_path = os.path.join(MUSIC_FOLDER, f"{safe_title}.mp3")  # Ruta final del archivo

    if os.path.exists(output_path):
        return output_path  # Retorna si ya fue descargado

    temp_path = os.path.join(MUSIC_FOLDER, f"temp_{safe_title}.%(ext)s")  # Ruta temporal

    # Opciones de configuración para yt_dlp
    ydl_opts = {
        'format': 'bestaudio/best',
        'outtmpl': temp_path,
        'postprocessors': [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
            'preferredquality': '192',
        }],
        'quiet': True,
        'retries': 10,
        'fragment-retries': 10,
        'extract-audio': True,
        'audio-format': 'mp3',
        'audio-quality': '0',
        'no-overwrites': True,
        'continue_dl': True,
        'ignoreerrors': True,
        'no-cache-dir': True,
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)  # Extrae metadata sin descargar
            if not info:
                raise Exception("No se pudo obtener información del video")

            ydl.download([url])  # Descarga el audio

            # Renombra el archivo temporal a .mp3 final
            for ext in ['.webm', '.m4a', '.mp3', '.part']:
                temp_file = temp_path.replace('%(ext)s', ext[1:])
                if os.path.exists(temp_file):
                    for _ in range(5):
                        try:
                            os.rename(temp_file, output_path)
                            break
                        except (PermissionError, OSError):
                            time.sleep(1)
                    else:
                        raise Exception(f"No se pudo renombrar el archivo: {temp_file}")
                    break

            if not os.path.exists(output_path):
                raise Exception("No se generó el archivo MP3")

            return output_path

    except Exception as e:
        # Limpia archivos temporales si hay error
        for ext in ['.webm', '.m4a', '.mp3', '.part']:
            temp_file = temp_path.replace('%(ext)s', ext[1:])
            if os.path.exists(temp_file):
                try:
                    os.remove(temp_file)
                except:
                    pass
        print(f"Error al descargar MP3: {e}")
        return None

# Obtiene info de la canción desde un texto (URL o búsqueda) y devuelve un NodoCancion
def obtener_info_cancion(texto):
    ydl_opts = {
        'format': 'bestaudio/best',
        'quiet': True,
        'noplaylist': True,
        'extract_flat': False,
        'default_search': 'ytsearch',
        'ignoreerrors': True,
        'retries': 10,
        'fragment-retries': 10,
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            for _ in range(3):  # Intenta 3 veces
                try:
                    info = ydl.extract_info(texto, download=False)  # Extrae metadata
                    if not info:
                        continue

                    if 'entries' in info:
                        info = info['entries'][0]  # Toma el primer resultado

                    titulo = info.get('title', 'Sin título')  # Título del video
                    miniatura = info.get('thumbnail', 'https://via.placeholder.com/200')  # Imagen
                    url = info.get('url') or info.get('webpage_url')  # URL de reproducción o descarga

                    if not url:
                        continue

                    file_path = descargar_mp3(url, titulo)  # Descarga el MP3
                    if not file_path:
                        continue

                    return NodoCancion(titulo, url, miniatura, file_path)  # Retorna el nodo

                except (yt_dlp.utils.DownloadError, yt_dlp.utils.ExtractorError) as e:
                    print(f"Intento fallido: {e}")
                    time.sleep(2)
                    continue

        raise Exception("No se pudo obtener información de la canción después de varios intentos")

    except Exception as e:
        raise Exception(f"Error al obtener información: {str(e)}")

def main(page: ft.Page):  # Función principal de la app, recibe la página de Flet
    global lista_reproduccion, player, reproduciendo  # Se usan variables globales para controlar el estado

    # Configuración general de la página
    page.title = "🎵 Reproductor Musical MP3"  # Título de la ventana
    page.theme_mode = ft.ThemeMode.DARK  # Tema oscuro
    page.horizontal_alignment = ft.CrossAxisAlignment.CENTER  # Alineación horizontal centrada
    page.scroll = ft.ScrollMode.AUTO  # Scroll automático si el contenido se desborda
    page.padding = 20  # Espaciado interno de la página
    page.window_min_width = 600  # Ancho mínimo de la ventana
    page.window_min_height = 700  # Alto mínimo de la ventana

    # Campo de texto para buscar canción o pegar una URL
    entrada_busqueda = ft.TextField(
        label="Buscar canción o pegar URL de YouTube",  # Etiqueta del campo
        width=500,  # Ancho del campo
        height=50,  # Alto del campo
        border_radius=10,  # Bordes redondeados
        filled=True,  # Fondo lleno
        prefix_icon=ft.icons.SEARCH,  # Icono de búsqueda al inicio
        autofocus=True  # Se enfoca automáticamente al iniciar
    )

    # Botón para agregar canción a la lista de reproducción
    boton_agregar = ft.ElevatedButton(
        text="Agregar a la lista",  # Texto del botón
        icon=ft.icons.ADD,  # Icono de suma
        on_click=lambda _: agregar_cancion(entrada_busqueda.value),  # Acción al hacer clic
        height=50,  # Alto del botón
        style=ft.ButtonStyle(
            shape=ft.RoundedRectangleBorder(radius=10),  # Borde redondeado
            padding=20  # Espaciado interno del botón
        )
    )

    # Texto que muestra el título de la canción actual
    texto_titulo = ft.Text(
        "No hay canciones en la lista",  # Texto por defecto
        size=24,  # Tamaño del texto
        weight=ft.FontWeight.BOLD,  # Texto en negrita
        text_align=ft.TextAlign.CENTER  # Alineación centrada
    )

    # Imagen de la miniatura de la canción actual
    imagen_cancion = ft.Image(
        src="https://via.placeholder.com/300",  # Imagen por defecto
        width=300,  # Ancho de la imagen
        height=300,  # Alto de la imagen
        fit=ft.ImageFit.CONTAIN,  # Ajuste de la imagen sin recortar
        border_radius=ft.border_radius.all(10)  # Bordes redondeados
    )

    def pausar(_=None):  # Función para pausar la reproducción
        global player  # Usamos la variable global del reproductor
        if player:  # Si hay una canción cargada
            player.toggle_pause()  # Alterna entre pausar y reanudar

    def detener(_=None):  # Función para detener la reproducción
        global player, reproduciendo  # Usamos variables globales
        if player:  # Si el reproductor está activo
            try:
                player.close_player()  # Cerramos el reproductor
            except:
                pass  # Ignoramos errores al cerrar
            player = None  # Limpiamos la variable del reproductor
        reproduciendo = False  # Indicamos que no se está reproduciendo

    def anterior(_=None):  # Función para ir a la canción anterior
        detener()  # Detenemos la canción actual
        lista_reproduccion.anterior()  # Movemos al nodo anterior
        tocar_actual()  # Reproducimos la nueva canción actual
        actualizar_lista_ui()  # Actualizamos la interfaz de la lista

    def siguiente(_=None):  # Función para ir a la canción siguiente
        detener()  # Detenemos la canción actual
        lista_reproduccion.siguiente()  # Movemos al nodo siguiente
        tocar_actual()  # Reproducimos la nueva canción actual
        actualizar_lista_ui()  # Actualizamos la interfaz de la lista

    def tocar_actual():  # Función para reproducir la canción actual
        global reproduciendo  # Variable global para controlar el estado de reproducción
        if not lista_reproduccion.actual:  # Si no hay canción actual
            return  # Salimos de la función

        detener()  # Detenemos cualquier reproducción previa
        cancion = lista_reproduccion.actual  # Obtenemos la canción actual

        texto_titulo.value = cancion.titulo  # Mostramos el título de la canción
        imagen_cancion.src = cancion.miniatura or "https://via.placeholder.com/300"  # Mostramos miniatura o imagen por defecto
        page.update()  # Actualizamos la interfaz

        if cancion.file_path and os.path.exists(cancion.file_path):  # Si el archivo ya está descargado
            reproduciendo = True  # Indicamos que estamos reproduciendo
            threading.Thread(target=reproducir_mp3, args=(cancion.file_path,), daemon=True).start()  # Reproducimos en un hilo separado

     # 2. Luego creamos los controles que usan estas funciones

    # Variable de estado para saber si está pausado
    estado_pausado = False

    # Botón para ir a la canción anterior
    boton_anterior = ft.IconButton(
        icon=ft.icons.SKIP_PREVIOUS,
        icon_size=40,
        tooltip="Canción anterior",
        on_click=anterior
    )

    # Botón para reproducir toda la lista, ubicado al extremo
    boton_play = ft.IconButton(
        icon=ft.icons.PLAY_ARROW,
        icon_size=50,
        tooltip="Reproducir",
        on_click=lambda _: tocar_actual(),
        style=ft.ButtonStyle(bgcolor=ft.colors.BLUE_700)
    )

    # Botón que alterna entre pausa y play
    boton_pausa = ft.IconButton(
        icon=ft.icons.PAUSE,
        icon_size=50,
        tooltip="Pausar",
        on_click=lambda _: alternar_pausa(),
        style=ft.ButtonStyle(bgcolor=ft.colors.AMBER_700)
    )

    # Botón para detener la reproducción
    boton_stop = ft.IconButton(
        icon=ft.icons.STOP,
        icon_size=50,
        tooltip="Detener",
        on_click=detener,
        style=ft.ButtonStyle(bgcolor=ft.colors.BLUE_700)
    )

    # Botón para ir a la siguiente canción
    boton_siguiente = ft.IconButton(
        icon=ft.icons.SKIP_NEXT,
        icon_size=40,
        tooltip="Siguiente canción",
        on_click=siguiente
    )

    # Función que alterna entre pausa y reproducción visualmente
    def alternar_pausa():
        global estado_pausado, player
        if estado_pausado:
            if player:
                player.set_pause(False)  # Reanuda
            boton_pausa.icon = ft.icons.PAUSE
            boton_pausa.tooltip = "Pausar"
            estado_pausado = False
        else:
            pausar()  # Pausa usando toggle
            boton_pausa.icon = ft.icons.PLAY_ARROW
            boton_pausa.tooltip = "Reanudar"
            estado_pausado = True
        page.update()

    # Contenedor de controles reorganizado

    controles_reproduccion = ft.Container(
        ft.Stack(
            [
                # Botones a la izquierda (play y stop)
                ft.Row(
                    [boton_play, boton_stop],
                    alignment=ft.MainAxisAlignment.START,
                ),
                # Botones centrados (anterior, pausa, siguiente)
                ft.Row(
                    [boton_anterior, boton_pausa, boton_siguiente],
                    alignment=ft.MainAxisAlignment.CENTER,
                    width=float("inf")  # Ocupa todo el ancho
                )
            ]
        ),
        margin=ft.margin.only(top=20, bottom=20),
        width=float("inf")
    )


    # Lista de reproducción canciones
    lista_canciones = ft.Column(  # Contenedor en columna para las canciones
        spacing=5,  # Espacio entre elementos
        scroll=ft.ScrollMode.AUTO,  # Activar scroll automático
        expand=True  # Que ocupe todo el espacio disponible
    )

    # Función para mover una canción hacia arriba en la lista
    def mover_arriba(cancion):
        if lista_reproduccion.longitud <= 1:  # No mover si solo hay una canción
            return

        canciones = lista_reproduccion.recorrer()  # Obtener la lista en orden
        current_index = canciones.index(cancion)  # Buscar el índice de la canción

        if current_index == 0:  # Ya está arriba del todo
            return

        # Obtener la canción anterior
        cancion_anterior = canciones[current_index-1]
        es_primera = (current_index == 1)  # Si está justo después de la actual
        es_ultima = (current_index == len(canciones)-1)  # Si es la última

        # Reconectar los enlaces para subirla en la lista
        cancion_anterior.anterior.siguiente = cancion  # El anterior del anterior apunta a esta
        cancion.anterior = cancion_anterior.anterior  # Esta apunta hacia arriba

        cancion_anterior.siguiente = cancion.siguiente  # El anterior conecta con el siguiente
        cancion.siguiente.anterior = cancion_anterior  # El siguiente conecta con el anterior

        cancion.siguiente = cancion_anterior  # Esta apunta al anterior (swap)
        cancion_anterior.anterior = cancion  # Y el anterior apunta a esta

        if es_primera:  # Si era la segunda en la lista
            lista_reproduccion.actual = cancion  # Ahora es la primera

        lista_reproduccion.guardar(PLAYLIST_FILE)  # Guardar cambios en archivo
        actualizar_lista_ui()  # Refrescar la interfaz

    # Función para mover una canción hacia abajo en la lista
    def mover_abajo(cancion):
        if lista_reproduccion.longitud <= 1:  # Si solo hay una canción, no se puede mover
            return

        canciones = lista_reproduccion.recorrer()  # Obtener la lista actual
        current_index = canciones.index(cancion)  # Obtener posición de la canción

        if current_index == len(canciones)-1:  # Ya está abajo del todo
            return

        cancion_siguiente = canciones[current_index+1]  # Obtener la siguiente canción
        es_primera = (current_index == 0)  # Si es la primera en la lista
        es_penultima = (current_index == len(canciones)-2)  # Si es la penúltima

        # Reconectar nodos para bajarla en la lista
        cancion.anterior.siguiente = cancion_siguiente  # El anterior apunta al siguiente
        cancion_siguiente.anterior = cancion.anterior  # El siguiente apunta al anterior

        cancion.siguiente = cancion_siguiente.siguiente  # Esta apunta al después del siguiente
        cancion_siguiente.siguiente.anterior = cancion  # El después del siguiente apunta a esta

        cancion_siguiente.siguiente = cancion  # El siguiente ahora apunta a esta
        cancion.anterior = cancion_siguiente  # Esta apunta al siguiente

        if es_primera and current_index == 0:  # Si era la primera
            lista_reproduccion.actual = cancion_siguiente  # La nueva primera es la siguiente

        lista_reproduccion.guardar(PLAYLIST_FILE)  # Guardar la lista
        actualizar_lista_ui()  # Refrescar la interfaz

    # Crear el contenedor visual para una canción individual
    def crear_item_lista(cancion):
        return ft.Container(  # Contenedor visual de la canción
            content=ft.Row(  # Organizado en fila
                [
                    ft.IconButton(  # Botón para subir
                        icon=ft.icons.ARROW_UPWARD,
                        on_click=lambda _, c=cancion: mover_arriba(c),  # Acción
                        tooltip="Mover arriba",  # Texto de ayuda
                        icon_size=20  # Tamaño del ícono
                    ),
                    ft.IconButton(  # Botón para bajar
                        icon=ft.icons.ARROW_DOWNWARD,
                        on_click=lambda _, c=cancion: mover_abajo(c),  # Acción
                        tooltip="Mover abajo",
                        icon_size=20
                    ),
                    ft.Text(cancion.titulo, expand=True, size=16),  # Título de la canción
                    ft.IconButton(  # Botón de eliminar
                        icon=ft.icons.DELETE,
                        tooltip="Eliminar",  # Texto de ayuda
                        on_click=lambda _, c=cancion: eliminar_cancion(c),  # Acción al clic
                        icon_color=ft.colors.RED_400  # Color del ícono
                    )
                ],
                alignment=ft.MainAxisAlignment.START,  # Alinear al inicio
                vertical_alignment=ft.CrossAxisAlignment.CENTER  # Centrado vertical
            ),
            padding=10,  # Relleno interior
            border_radius=5,  # Bordes redondeados
            bgcolor=ft.colors.GREY_900 if lista_reproduccion.actual == cancion else ft.colors.GREY_800,  # Color de fondo
            border=ft.border.all(1, ft.colors.GREY_700)  # Borde con color
        )

     # Función para actualizar visualmente la lista de reproducción
    def actualizar_lista_ui():
        lista_canciones.controls.clear()  # Limpiamos todos los controles actuales de la lista
        for cancion in lista_reproduccion.recorrer():  # Recorremos todas las canciones de la lista
            lista_canciones.controls.append(crear_item_lista(cancion))  # Creamos y agregamos el ítem visual de cada canción
        page.update()  # Actualizamos la página para reflejar los cambios

    # Muestra un mensaje de error en un SnackBar
    def mostrar_error(mensaje):
        page.snack_bar = ft.SnackBar(ft.Text(mensaje))  # Creamos el SnackBar con el mensaje
        page.snack_bar.open = True  # Lo abrimos
        page.update()  # Actualizamos la página

    # Función que reproduce un archivo MP3 usando ffpyplayer
    def reproducir_mp3(file_path):
        global player, reproduciendo  # Usamos las variables globales
        try:
            player = MediaPlayer(file_path)  # Creamos el reproductor con el archivo
            while reproduciendo and player:  # Mientras siga reproduciendo y exista el reproductor
                frame, val = player.get_frame()  # Obtenemos el siguiente frame de audio
                if val == 'eof':  # Si llega al final del archivo
                    siguiente()  # Pasamos a la siguiente canción
                    break  # Salimos del bucle
                time.sleep(0.01)  # Esperamos un poco para no bloquear el hilo
        except Exception as e:
            print(f"Error de reproducción: {e}")  # Mostramos el error en consola
            siguiente()  # Pasamos a la siguiente canción

    # Función para reproducir la canción actual (verificada)
    def tocar_actual():
        global reproduciendo  # Usamos la variable global

        if not lista_reproduccion.actual:
            return  # Si no hay canción actual, salimos

        detener()  # Detenemos la canción actual

        cancion = lista_reproduccion.actual  # Obtenemos la canción actual

        texto_titulo.value = cancion.titulo  # Mostramos el título
        imagen_cancion.src = cancion.miniatura or "https://via.placeholder.com/300"  # Mostramos la miniatura
        page.update()  # Actualizamos la UI

        # Si ya está descargada localmente
        if cancion.file_path and os.path.exists(cancion.file_path):
            reproduciendo = True  # Marcamos que estamos reproduciendo
            threading.Thread(target=reproducir_mp3, args=(cancion.file_path,), daemon=True).start()  # Reproducimos en otro hilo
        else:
            try:
                file_path = descargar_mp3(cancion.url, cancion.titulo)  # Descargamos la canción desde YouTube
                if file_path:  # Si la descarga fue exitosa
                    cancion.file_path = file_path  # Guardamos la ruta en el objeto canción
                    lista_reproduccion.guardar(PLAYLIST_FILE)  # Guardamos la lista actualizada
                    reproduciendo = True  # Marcamos que se está reproduciendo
                    threading.Thread(target=reproducir_mp3, args=(file_path,), daemon=True).start()  # Reproducimos
                else:
                    mostrar_error("No se pudo descargar el archivo MP3")  # Mostramos error si no se pudo descargar
            except Exception as e:
                mostrar_error(f"Error al descargar MP3: {e}")  # Mostramos cualquier otro error

    # Función para pausar la reproducción
    def pausar(_=None):
        global player  # Usamos el reproductor global
        if player:
            player.toggle_pause()  # Alternamos entre pausar y reanudar

    # Función para detener la reproducción completamente
    def detener(_=None):
        global player, reproduciendo  # Usamos variables globales
        if player:
            try:
                player.close_player()  # Cerramos el reproductor
            except:
                pass  # Ignoramos errores al cerrar
            player = None  # Eliminamos la instancia del reproductor
        reproduciendo = False  # Indicamos que no se está reproduciendo

    # Reproduce la siguiente canción
    def siguiente(_=None):
        detener()  # Detenemos la actual
        lista_reproduccion.siguiente()  # Avanzamos al siguiente nodo
        tocar_actual()  # Reproducimos la nueva canción
        actualizar_lista_ui()  # Actualizamos la UI

    # Reproduce la canción anterior
    def anterior(_=None):
        detener()  # Detenemos la actual
        lista_reproduccion.anterior()  # Retrocedemos un nodo
        tocar_actual()  # Reproducimos la nueva canción
        actualizar_lista_ui()  # Actualizamos la UI

    # Agrega una canción desde un texto o URL
    def agregar_cancion(texto):
        texto = texto.strip()  # Eliminamos espacios en blanco
        if not texto:
            return  # Si está vacío, salimos

        page.splash = ft.ProgressBar()  # Mostramos barra de carga
        entrada_busqueda.disabled = True  # Desactivamos la entrada
        boton_agregar.disabled = True  # Desactivamos el botón
        page.update()  # Actualizamos la UI

        try:
            cancion = obtener_info_cancion(texto)  # Obtenemos info de la canción desde YouTube o búsqueda
            lista_reproduccion.agregar(cancion)  # La agregamos a la lista
            lista_reproduccion.guardar(PLAYLIST_FILE)  # Guardamos la lista actualizada
            actualizar_lista_ui()  # Actualizamos la UI

            if lista_reproduccion.longitud == 1:
                tocar_actual()  # Si es la primera canción, la reproducimos

        except Exception as e:
            mostrar_error(f"Error al agregar canción: {str(e)}")  # Mostramos el error

        finally:
            page.splash = None  # Quitamos la barra de carga
            entrada_busqueda.disabled = False  # Activamos la entrada
            boton_agregar.disabled = False  # Activamos el botón
            entrada_busqueda.value = ""  # Borramos el texto ingresado
            page.update()  # Actualizamos la UI

    # Elimina una canción de la lista
    def eliminar_cancion(cancion):
        global player, reproduciendo  # Usamos variables globales

        if lista_reproduccion.actual == cancion:  # Si la canción eliminada es la actual
            if lista_reproduccion.longitud == 1:
                detener()  # Si era la única canción, detenemos todo
                lista_reproduccion.actual = None  # Borramos la referencia
                lista_reproduccion.longitud = 0  # Reiniciamos la longitud
            else:
                siguiente()  # Si hay más, pasamos a la siguiente

        lista_reproduccion.eliminar(cancion)  # Eliminamos la canción de la lista
        lista_reproduccion.guardar(PLAYLIST_FILE)  # Guardamos la lista modificada
        actualizar_lista_ui()  # Actualizamos la UI

        if lista_reproduccion.longitud == 0:
            texto_titulo.value = "No hay canciones en la lista"  # Mostramos mensaje vacío
            imagen_cancion.src = "https://via.placeholder.com/300"  # Imagen por defecto
            page.update()  # Actualizamos la UI

    # Tarjeta superior con el campo de búsqueda y el botón de agregar
    barra_busqueda = ft.Card(
        content=ft.Container(
            ft.Row([entrada_busqueda, boton_agregar], alignment=ft.MainAxisAlignment.CENTER, spacing=10),  # Fila con el campo y el botón
            padding=15  # Espaciado interno
        ),
        elevation=5,  # Sombra de la tarjeta
        margin=ft.margin.only(bottom=20)  # Margen inferior
    )

    # Tarjeta con el título, miniatura y controles de reproducción
    panel_info = ft.Card(
        content=ft.Container(
            ft.Column([texto_titulo, imagen_cancion, controles_reproduccion],  # Columna con título, imagen y botones
                horizontal_alignment=ft.CrossAxisAlignment.CENTER, spacing=10),  # Alineado y espaciado
            padding=20  # Espaciado interno
        ),
        elevation=5,  # Sombra
        margin=ft.margin.only(bottom=20)  # Margen inferior
    )

    # Tarjeta para mostrar la lista de canciones
    panel_lista = ft.Card(
        content=ft.Container(
            ft.Column([
                ft.Text("Lista de Reproducción", size=18, weight=ft.FontWeight.BOLD),  # Título de la lista
                ft.Divider(height=10, color=ft.colors.TRANSPARENT),  # Separador invisible para espaciado
                lista_canciones  # Componente que contiene la lista
            ], expand=True),  # La columna ocupa todo el espacio posible
            padding=15  # Espaciado interno
        ),
        elevation=5,  # Sombra
        expand=True  # La tarjeta ocupa todo el espacio vertical disponible
    )

    # Agregamos todos los paneles a la página principal en una columna
    page.add(
        ft.Column([barra_busqueda, panel_info, panel_lista], expand=True, spacing=20)  # Columna con separación y expansión
    )

    # Cargamos la lista de reproducción desde archivo
    lista_reproduccion.cargar(PLAYLIST_FILE)  # Intenta cargar el archivo con las canciones
    actualizar_lista_ui()  # Refresca la lista en pantalla

    # Si hay canciones, comenzamos a reproducir la actual
    if lista_reproduccion.longitud > 0:
        tocar_actual()  # Inicia reproducción de la canción actual

ft.app(target=main) 