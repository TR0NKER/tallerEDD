
import flet as ft 

from ffpyplayer.player import MediaPlayer 
import yt_dlp 

import threading  
import subprocess

import time  

import json  
import os 

estado_pausado = False  

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
MUSIC_FOLDER = os.path.join(BASE_DIR, "music")
PLAYLIST_FILE = os.path.join(BASE_DIR, "playlist.json")

class NodoCancion:
    def __init__(self, titulo, url, miniatura, file_path=None):
        self.titulo = titulo  
        self.url = url 
        self.miniatura = miniatura 
        self.file_path = file_path  

        self.anterior = None 
        self.siguiente = None  

    def to_dict(self):
        return {
            "titulo": self.titulo,
            "url": self.url,
            "miniatura": self.miniatura,
            "file_path": self.file_path
        }  # Convierte el nodo en un diccionario 

    @staticmethod
    def from_dict(data):
        return NodoCancion(
            data["titulo"],
            data["url"],
            data["miniatura"],
            data.get("file_path")
        )  # Crea un nodo desde un diccionario 

class ListaReproduccion:
    def __init__(self):
        self.PTR = None 
        self.longitud = 0  

    def agregar(self, cancion):
        if not self.PTR:
            self.PTR = cancion  
            cancion.siguiente = cancion.anterior = cancion 
        else:
            FINAL = self.PTR.anterior 
            FINAL.siguiente = cancion  
            cancion.anterior = FINAL 
            cancion.siguiente = self.PTR  
            self.PTR.anterior = cancion  

        self.longitud += 1  

    def eliminar(self, cancion):
        if self.longitud == 0:
            return  
        
        if self.longitud == 1 and self.PTR == cancion:
            self.PTR = None  
        else:
            if self.PTR == cancion:
                self.PTR = cancion.siguiente

            cancion.anterior.siguiente = cancion.siguiente  
            cancion.siguiente.anterior = cancion.anterior

        self.longitud -= 1 

        if cancion.file_path and os.path.exists(cancion.file_path):
            try:
                os.remove(cancion.file_path)
            except Exception as e:
                print(f"Error al eliminar archivo: {e}")

    def siguiente(self):
        if self.PTR:
            self.PTR = self.PTR.siguiente  

    def anterior(self):
        if self.PTR:
            self.PTR = self.PTR.anterior  

    def recorrer(self):
        canciones = []
        if self.PTR:
            nodo = self.PTR
            for _ in range(self.longitud):  
                canciones.append(nodo)
                nodo = nodo.siguiente
        return canciones  

    def vaciar(self):
        for cancion in self.recorrer():  
            if cancion.file_path and os.path.exists(cancion.file_path):
                try:
                    os.remove(cancion.file_path)
                except Exception as e:
                    print(f"Error al eliminar archivo: {e}")
        self.PTR = None  
        self.longitud = 0

    def guardar(self, archivo):
        with open(archivo, "w", encoding="utf-8") as f:
            json.dump([c.to_dict() for c in self.recorrer()], f, ensure_ascii=False, indent=2)

    def cargar(self, archivo):
        if not os.path.exists(archivo):
            return  
        self.vaciar()
        with open(archivo, "r", encoding="utf-8") as f:
            datos = json.load(f)
            for d in datos:
                if "file_path" in d and d["file_path"] and not os.path.exists(d["file_path"]):
                    d["file_path"] = None
                self.agregar(NodoCancion.from_dict(d)) 

lista_reproduccion = ListaReproduccion()  
player = None 
reproduciendo = False  

if not os.path.exists(MUSIC_FOLDER):
    os.makedirs(MUSIC_FOLDER)

def descargar_mp3(url, titulo):
    safe_title = "".join(c for c in titulo if c.isalnum() or c in " -_").rstrip() 
    output_path = os.path.join(MUSIC_FOLDER, f"{safe_title}.mp3")  

    if os.path.exists(output_path):
        return output_path  

    temp_path = os.path.join(MUSIC_FOLDER, f"temp_{safe_title}.%(ext)s")  

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
            info = ydl.extract_info(url, download=False)  
            if not info:
                raise Exception("No se pudo obtener información del video")

            ydl.download([url])  

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
        
        for ext in ['.webm', '.m4a', '.mp3', '.part']:
            temp_file = temp_path.replace('%(ext)s', ext[1:])
            if os.path.exists(temp_file):
                try:
                    os.remove(temp_file)
                except:
                    pass
        print(f"Error al descargar MP3: {e}")
        return None

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
            for _ in range(3): 
                try:
                    info = ydl.extract_info(texto, download=False)  
                    if not info:
                        continue

                    if 'entries' in info:
                        info = info['entries'][0]  

                    titulo = info.get('title', 'Sin título')  
                    miniatura = info.get('thumbnail', 'https://via.placeholder.com/200') 
                    url = info.get('url') or info.get('webpage_url')  

                    if not url:
                        continue

                    file_path = descargar_mp3(url, titulo)  
                    if not file_path:
                        continue

                    return NodoCancion(titulo, url, miniatura, file_path)  

                except (yt_dlp.utils.DownloadError, yt_dlp.utils.ExtractorError) as e:
                    print(f"Intento fallido: {e}")
                    time.sleep(2)
                    continue

        raise Exception("No se pudo obtener información de la canción después de varios intentos")

    except Exception as e:
        raise Exception(f"Error al obtener información: {str(e)}")




def main(page: ft.Page):  
    global lista_reproduccion, player, reproduciendo  

    page.title = "🎵 Reproductor Musical"  
    page.theme_mode = ft.ThemeMode.DARK  
    page.horizontal_alignment = ft.CrossAxisAlignment.CENTER  
    page.scroll = ft.ScrollMode.AUTO  
    page.padding = 20  
    page.window_min_width = 600  
    page.window_min_height = 700  

    entrada_busqueda = ft.TextField(
        label="Buscar canción o pegar URL de YouTube",  
        width=500,  
        height=50,  
        border_radius=10,  
        filled=True,  
        prefix_icon=ft.icons.SEARCH,  
        autofocus=True  
    )

    boton_agregar = ft.ElevatedButton(
        text="Agregar a la lista", 
        icon=ft.icons.ADD,
        on_click=lambda _: agregar_cancion(entrada_busqueda.value),  
        height=50,  
        style=ft.ButtonStyle(
            shape=ft.RoundedRectangleBorder(radius=10),  
            padding=20  
        )
    )

    texto_titulo = ft.Text(
        "No hay canciones en la lista", 
        size=24,  
        weight=ft.FontWeight.BOLD,  
        text_align=ft.TextAlign.CENTER  
    )

    imagen_cancion = ft.Image(
        src="https://via.placeholder.com/300",  
        width=300, 
        height=300,  
        fit=ft.ImageFit.CONTAIN,  
        border_radius=ft.border_radius.all(10)  
    )

    def pausar(_=None): 
        global player  
        if player:  
            player.toggle_pause()  

    def detener(_=None):  
        global player, reproduciendo  
        if player:  
            try:
                player.close_player()  
            except:
                pass  
            player = None  
        reproduciendo = False  

    def anterior(_=None):  
        detener()  
        lista_reproduccion.anterior()  
        tocar_actual()  
        actualizar_lista_ui()  

    def siguiente(_=None):  
        detener()  
        lista_reproduccion.siguiente()  
        tocar_actual()  
        actualizar_lista_ui()  

    

    boton_anterior = ft.IconButton(
        icon=ft.icons.SKIP_PREVIOUS,
        icon_size=40,
        tooltip="Canción anterior",
        on_click=anterior
    )

    boton_play = ft.IconButton(
        icon=ft.icons.PLAY_ARROW,
        icon_size=50,
        tooltip="Reproducir",
        on_click=lambda _: tocar_actual(),
        style=ft.ButtonStyle(bgcolor=ft.colors.BLUE_700)
    )

    boton_pausa = ft.IconButton(
        icon=ft.icons.PAUSE,
        icon_size=50,
        tooltip="Pausar",
        on_click=lambda _: alternar_pausa(),
        style=ft.ButtonStyle(bgcolor=ft.colors.AMBER_700)
    )

    boton_stop = ft.IconButton(
        icon=ft.icons.STOP,
        icon_size=50,
        tooltip="Detener",
        on_click=detener,
        style=ft.ButtonStyle(bgcolor=ft.colors.BLUE_700)
    )

    boton_siguiente = ft.IconButton(
        icon=ft.icons.SKIP_NEXT,
        icon_size=40,
        tooltip="Siguiente canción",
        on_click=siguiente
    )

    def alternar_pausa():
        global estado_pausado, player
        if estado_pausado:
            if player:
                player.set_pause(False)  
            boton_pausa.icon = ft.icons.PAUSE
            boton_pausa.tooltip = "Pausar"
            estado_pausado = False
        else:
            pausar() 
            boton_pausa.icon = ft.icons.PLAY_ARROW
            boton_pausa.tooltip = "Reanudar"
            estado_pausado = True
        page.update()

    controles_reproduccion = ft.Container(
        ft.Stack(
            [
                ft.Row(
                    [boton_play, boton_stop],
                    alignment=ft.MainAxisAlignment.START,
                ),
                ft.Row(
                    [boton_anterior, boton_pausa, boton_siguiente],
                    alignment=ft.MainAxisAlignment.CENTER,
                    width=float("inf")  
                )
            ]
        ),
        margin=ft.margin.only(top=20, bottom=20),
        width=float("inf")
    )

    lista_canciones = ft.Column(  
        spacing=5,  
        scroll=ft.ScrollMode.AUTO,  
        expand=True  
    )

    def mover_arriba(cancion):
        if lista_reproduccion.longitud <= 1:  
            return

        canciones = lista_reproduccion.recorrer()  
        current_index = canciones.index(cancion)  

        if current_index == 0:  
            return

        cancion_anterior = canciones[current_index-1]
        es_primera = (current_index == 1)  

        cancion_anterior.anterior.siguiente = cancion 
        cancion.anterior = cancion_anterior.anterior  

        cancion_anterior.siguiente = cancion.siguiente  
        cancion.siguiente.anterior = cancion_anterior  

        cancion.siguiente = cancion_anterior 
        cancion_anterior.anterior = cancion 

        if es_primera:  
            lista_reproduccion.PTR = cancion  

        lista_reproduccion.guardar(PLAYLIST_FILE) 
        actualizar_lista_ui()

    def mover_abajo(cancion):
        if lista_reproduccion.longitud <= 1:  
            return

        canciones = lista_reproduccion.recorrer()  
        current_index = canciones.index(cancion) 

        if current_index == len(canciones)-1:  
            return

        cancion_siguiente = canciones[current_index+1]  
        es_primera = (current_index == 0)  

        cancion.anterior.siguiente = cancion_siguiente  
        cancion_siguiente.anterior = cancion.anterior  

        cancion.siguiente = cancion_siguiente.siguiente  
        cancion_siguiente.siguiente.anterior = cancion  

        cancion_siguiente.siguiente = cancion  
        cancion.anterior = cancion_siguiente  

        if es_primera and current_index == 0:  
            lista_reproduccion.PTR = cancion_siguiente  

        lista_reproduccion.guardar(PLAYLIST_FILE)  
        actualizar_lista_ui()  

    def crear_item_lista(cancion):
        return ft.Container(  
            content=ft.Row(  
                [
                    ft.IconButton(  
                        icon=ft.icons.ARROW_UPWARD,
                        on_click=lambda _, c=cancion: mover_arriba(c),  
                        tooltip="Mover arriba",  
                        icon_size=20  
                    ),
                    ft.IconButton(  
                        icon=ft.icons.ARROW_DOWNWARD,
                        on_click=lambda _, c=cancion: mover_abajo(c), 
                        tooltip="Mover abajo",
                        icon_size=20
                    ),
                    ft.Text(cancion.titulo, expand=True, size=16),  

                    ft.IconButton(  
                        icon=ft.icons.DELETE,
                        tooltip="Eliminar", 
                        on_click=lambda _, c=cancion: eliminar_cancion(c),  
                        icon_color=ft.colors.RED_400  
                    )
                ],
                alignment=ft.MainAxisAlignment.START,  
                vertical_alignment=ft.CrossAxisAlignment.CENTER  
            ),
            padding=10,  
            border_radius=5,  
            bgcolor=ft.colors.GREY_900 if lista_reproduccion.PTR == cancion else ft.colors.GREY_800,  
            border=ft.border.all(1, ft.colors.GREY_700)  
        )

    def actualizar_lista_ui():
        lista_canciones.controls.clear()  
        for cancion in lista_reproduccion.recorrer():  
            lista_canciones.controls.append(crear_item_lista(cancion))  
        page.update() 

    def mostrar_error(mensaje):
        page.snack_bar = ft.SnackBar(ft.Text(mensaje))  
        page.snack_bar.open = True  
        page.update()  

    def obtener_duracion(file_path):
        try:
            cmd = [
                'ffprobe', '-v', 'error', 
                '-show_entries', 'format=duration', 
                '-of', 'default=noprint_wrappers=1:nokey=1', 
                file_path
            ]
            result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            return float(result.stdout.strip())
        except:
            return None  

    def reproducir_mp3(file_path):
        
        global player, reproduciendo
        
        duracion = obtener_duracion(file_path)
        
        if duracion is None:
            print("¡Error! No se pudo obtener la duración. Usando valor por defecto (3 mins)")
            duracion = 300  
        
        print(f"Duración detectada: {duracion:.2f} segundos")
        
        player = MediaPlayer(file_path)
        inicio = time.time()
        
        try:
            reproduciendo = True     
            tiempo_transcurrido = 0.0

            ultimo_reloj = time.time()

            while reproduciendo:
                tiempo_actual = time.time()
                
                if not (boton_pausa.icon == ft.icons.PLAY_ARROW):
                    delta = tiempo_actual - ultimo_reloj
                    tiempo_transcurrido += delta
                    
                    if tiempo_transcurrido >= duracion - 1:
                        print(f"Cambiando 1s antes del final (Tiempo: {tiempo_transcurrido:.2f}s)")
                        siguiente()  
                        break
                
                ultimo_reloj = tiempo_actual
                
                time.sleep(0.1)
        
        except Exception as e:
            print(f"Error: {e}")
            siguiente()
        finally:
            if player:
                player.close_player()
            print(f"Reproducción finalizada. Tiempo total: {time.time() - inicio:.2f}s")

    def tocar_actual():
        
        global reproduciendo  

        if not lista_reproduccion.PTR:
            return  
        detener() 

        cancion = lista_reproduccion.PTR  

        texto_titulo.value = cancion.titulo  
        imagen_cancion.src = cancion.miniatura or "https://via.placeholder.com/300" 
        page.update()  

        if cancion.file_path and os.path.exists(cancion.file_path):
            reproduciendo = True  
            threading.Thread(target=reproducir_mp3, args=(cancion.file_path,), daemon=True).start()  
        else:
            try:
                file_path = descargar_mp3(cancion.url, cancion.titulo)  
                if file_path:  
                    cancion.file_path = file_path  
                    lista_reproduccion.guardar(PLAYLIST_FILE) 
                    reproduciendo = True  
                    threading.Thread(target=reproducir_mp3, args=(file_path,), daemon=True).start()  
                else:
                    mostrar_error("No se pudo descargar el archivo MP3")  
            except Exception as e:
                mostrar_error(f"Error al descargar MP3: {e}")  

    def agregar_cancion(texto):
        texto = texto.strip() 
        if not texto:
            return  

        page.splash = ft.ProgressBar()  
        entrada_busqueda.disabled = True  
        boton_agregar.disabled = True  
        page.update()  

        try:
            cancion = obtener_info_cancion(texto)  
            lista_reproduccion.agregar(cancion)  
            lista_reproduccion.guardar(PLAYLIST_FILE)  
            actualizar_lista_ui() 

            if lista_reproduccion.longitud == 1:
                tocar_actual()  

        except Exception as e:
            mostrar_error(f"Error al agregar canción: {str(e)}") 

        finally:
            page.splash = None  
            entrada_busqueda.disabled = False  
            boton_agregar.disabled = False  
            entrada_busqueda.value = ""  
            page.update()  

    def eliminar_cancion(cancion):
        global player, reproduciendo  

        if lista_reproduccion.PTR == cancion:  
            if lista_reproduccion.longitud == 1:
                detener()  
                lista_reproduccion.PTR = None  
                lista_reproduccion.longitud = 0 
            else:
                siguiente() 

        lista_reproduccion.eliminar(cancion)  
        lista_reproduccion.guardar(PLAYLIST_FILE)  
        actualizar_lista_ui()  

        if lista_reproduccion.longitud == 0:
            texto_titulo.value = "No hay canciones en la lista"  
            imagen_cancion.src = "https://via.placeholder.com/300" 
            page.update() 

    barra_busqueda = ft.Card(
        content=ft.Container(
            ft.Row([entrada_busqueda, boton_agregar], alignment=ft.MainAxisAlignment.CENTER, spacing=10), 
            padding=15  
        ),
        elevation=5,
        margin=ft.margin.only(bottom=20) 
    )

    panel_info = ft.Card(
        content=ft.Container(
            ft.Column([texto_titulo, imagen_cancion, controles_reproduccion],  
                horizontal_alignment=ft.CrossAxisAlignment.CENTER, spacing=10), 
            padding=20  
        ),
        elevation=5, 
        margin=ft.margin.only(bottom=20)  
    )

    panel_lista = ft.Card(
        content=ft.Container(
            ft.Column([
                ft.Text("Lista de Reproducción", size=18, weight=ft.FontWeight.BOLD),  
                ft.Divider(height=10, color=ft.colors.TRANSPARENT),  
                lista_canciones  
            ], 
            expand=True),  
            padding=15  
        ),
        elevation=5,  
        expand=True 
    )
    
    panel_contacto = ft.Container(
        content=ft.Column(
            controls=[
                ft.Text("Informacion de contacto:"),
                ft.Text("Juan Arrieta - coleyf@uninorte.edu.co"),
                ft.Text("Jeronimo Castro - jeronimoac@uninorte.edu.co"),
                ft.Text("Angelo De Leon - canedaa@uninorte.edu.co"),
                ft.Text("Santiago Camacho - scarta@uninorte.edu.co"),
            ],
            alignment=ft.MainAxisAlignment.CENTER,
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
        ),
        alignment=ft.alignment.center, 
        expand=True                    
    )

    page.add(
        ft.Column([barra_busqueda, panel_info, panel_lista, panel_contacto], expand=True, spacing=20)  
    )

    lista_reproduccion.cargar(PLAYLIST_FILE)  
    actualizar_lista_ui()  

    if lista_reproduccion.longitud > 0:
        tocar_actual() 

ft.app(target=main) 