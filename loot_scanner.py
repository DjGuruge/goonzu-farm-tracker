"""
GoonZu Farm Tracker - Loot Scanner
Real-time memory scanner for GoonZu.exe loot drops
Supports multiple client instances with process selection
"""

import re
import sqlite3
import time
import sys
import argparse
from datetime import datetime
from typing import List, Dict, Optional, Tuple
import os

try:
    import psutil
    PSUTIL_AVAILABLE = True
except ImportError:
    PSUTIL_AVAILABLE = False
    print("Warning: psutil not installed. Run: pip install psutil")

try:
    import win32api
    import win32process
    import win32con
    from ctypes import windll, c_void_p, c_size_t, c_ubyte, c_int, byref, create_string_buffer
    WIN32_AVAILABLE = True
except ImportError:
    WIN32_AVAILABLE = False
    print("Warning: pywin32 not installed. Run: pip install pywin32")

# Windows API constants
PROCESS_VM_READ = 0x0010
PROCESS_QUERY_INFORMATION = 0x0400
PROCESS_VM_OPERATION = 0x0008

# Pattern to match loot drops in memory
DROP_PATTERN = re.compile(r'Obtained \[([^\]]+)\] (\d+) unit\(s\)\.\(price: ([\d,\.]+)\[M\]\)')


def find_goonzu_processes() -> List[Dict]:
    """
    Trova tutti i processi GoonZu.exe in esecuzione
    
    Returns:
        Lista di dizionari con informazioni sui processi trovati
    """
    if not PSUTIL_AVAILABLE:
        print("Errore: psutil non disponibile. Impossibile trovare i processi.")
        return []
    
    processes = []
    for proc in psutil.process_iter(['pid', 'name', 'memory_info', 'create_time']):
        try:
            if proc.info['name'] and proc.info['name'].lower() == 'goonzu.exe':
                memory_mb = proc.info['memory_info'].rss / 1024 / 1024 if proc.info['memory_info'] else 0
                processes.append({
                    'pid': proc.info['pid'],
                    'name': proc.info['name'],
                    'memory_usage': round(memory_mb, 2),
                    'start_time': datetime.fromtimestamp(proc.info['create_time']).strftime('%Y-%m-%d %H:%M:%S')
                })
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            continue
    return processes


def list_processes():
    """Stampa la lista dei processi GoonZu trovati"""
    processes = find_goonzu_processes()
    if not processes:
        print("Nessun processo GoonZu.exe trovato.")
        print("Assicurati che GoonZu sia in esecuzione.")
        return False
    
    print(f"\n{'='*60}")
    print(f"Trovati {len(processes)} processo/i GoonZu.exe:")
    print(f"{'='*60}")
    for i, proc in enumerate(processes, 1):
        print(f"{i}. PID: {proc['pid']:6d} | Memoria: {proc['memory_usage']:8.2f} MB | Avviato: {proc['start_time']}")
    print(f"{'='*60}\n")
    return True


class LootScanner:
    """Scanner di memoria per GoonZu.exe con supporto per selezione processo"""
    
    def __init__(self, target_pid: Optional[int] = None, db_path: str = "loot.db"):
        """
        Inizializza lo scanner
        
        Args:
            target_pid: PID del processo da tracciare (None = automatico)
            db_path: Percorso del database SQLite
        """
        self.target_pid = target_pid
        self.db_path = db_path
        self.process_handle = None
        self.scanning = False
        self.session_id = None
        self.process_name = "GoonZu.exe"
        
        # Cache per evitare duplicati (memoria degli ultimi drop)
        self.last_drops = {}  # {text: timestamp}
        self.dedupe_window = 2  # secondi
        
        if not WIN32_AVAILABLE:
            print("Errore: librerie Windows non disponibili. Lo scanner non funzionerà.")
        
    def attach_to_process(self) -> bool:
        """
        Si attacca al processo GoonZu specificato o al primo trovato
        
        Returns:
            True se l'attacco è riuscito, False altrimenti
        """
        if not WIN32_AVAILABLE:
            return False
        
        # Trova i processi disponibili
        processes = find_goonzu_processes()
        if not processes:
            print("❌ Nessun processo GoonZu.exe trovato.")
            print("   Assicurati che GoonZu sia in esecuzione e riprova.")
            return False
        
        # Se non è specificato un PID, usa il primo disponibile
        if self.target_pid is None:
            self.target_pid = processes[0]['pid']
            print(f"📌 Nessun PID specificato. Utilizzo processo predefinito:")
            print(f"   PID: {self.target_pid} | Memoria: {processes[0]['memory_usage']} MB")
        else:
            # Verifica che il PID specificato esista
            valid_pids = [p['pid'] for p in processes]
            if self.target_pid not in valid_pids:
                print(f"❌ PID {self.target_pid} non trovato.")
                print(f"   PID disponibili: {valid_pids}")
                print("\nProcessi trovati:")
                for proc in processes:
                    print(f"   • PID {proc['pid']} - Memoria: {proc['memory_usage']} MB")
                return False
        
        # Apri il processo con i permessi necessari
        try:
            self.process_handle = win32api.OpenProcess(
                PROCESS_VM_READ | PROCESS_QUERY_INFORMATION,
                False,
                self.target_pid
            )
            if not self.process_handle:
                print(f"❌ Impossibile aprire il processo PID {self.target_pid}")
                print("   Esegui il programma come Amministratore (Run as Administrator)")
                return False
            
            print(f"✅ Attaccato al processo PID {self.target_pid} (GoonZu.exe)")
            return True
            
        except Exception as e:
            print(f"❌ Errore nell'apertura del processo: {e}")
            print("   Assicurati di eseguire come Amministratore")
            return False
    
    def read_memory(self, address: int, size: int) -> Optional[bytes]:
        """
        Legge la memoria del processo all'indirizzo specificato
        
        Args:
            address: Indirizzo di memoria da leggere
            size: Numero di byte da leggere
            
        Returns:
            Bytes letti o None in caso di errore
        """
        if not self.process_handle:
            return None
        
        try:
            # Usa ReadProcessMemory tramite ctypes per maggior controllo
            kernel32 = windll.kernel32
            buffer = create_string_buffer(size)
            bytes_read = c_size_t(0)
            
            if kernel32.ReadProcessMemory(
                self.process_handle.handle,
                c_void_p(address),
                buffer,
                c_size_t(size),
                byref(bytes_read)
            ):
                return buffer.raw[:bytes_read.value]
        except Exception as e:
            # Silenzia errori di lettura memoria (normali durante scansione)
            pass
        
        return None
    
    def scan_for_drops(self, chunk_size: int = 4096) -> List[Tuple[str, int, float]]:
        """
        Scansiona la memoria del processo alla ricerca di drop
        
        Args:
            chunk_size: Dimensione dei chunk di memoria da leggere
            
        Returns:
            Lista di tuple (item, quantity, price)
        """
        if not self.process_handle:
            return []
        
        drops = []
        current_time = time.time()
        
        # Metodo semplificato: cerca pattern nelle regioni di memoria
        # Nota: Una implementazione completa richiederebbe di enumerare
        # le regioni di memoria del processo. Questa è una versione base.
        
        try:
            # Leggi un range di memoria tipico per GoonZu (esempio)
            # In produzione, dovresti enumerare le regioni di memoria
            base_addresses = [0x00400000, 0x00500000, 0x00600000]  # Esempi
            
            for base_addr in base_addresses:
                for offset in range(0, 0x100000, chunk_size):
                    addr = base_addr + offset
                    data = self.read_memory(addr, chunk_size)
                    
                    if data:
                        try:
                            # Decodifica come testo (ignora errori)
                            text = data.decode('utf-8', errors='ignore')
                            
                            # Cerca pattern nei dati letti
                            for match in DROP_PATTERN.finditer(text):
                                item = match.group(1)
                                quantity = int(match.group(2))
                                price_str = match.group(3).replace(',', '')
                                price = float(price_str)
                                
                                # Deduplica drop recenti
                                drop_key = f"{item}_{quantity}_{price}"
                                if drop_key not in self.last_drops or \
                                   (current_time - self.last_drops[drop_key]) > self.dedupe_window:
                                    self.last_drops[drop_key] = current_time
                                    drops.append((item, quantity, price))
                                    print(f"🎯 Drop trovato: {item} x{quantity} @ {price}M")
                        except:
                            pass
                            
        except Exception as e:
            # Silenzia errori generici durante scansione
            pass
        
        return drops
    
    def save_drop(self, item: str, quantity: int, price: float):
        """
        Salva un drop nel database SQLite
        
        Args:
            item: Nome dell'item
            quantity: Quantità
            price: Prezzo in milioni
        """
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # Assicura che la tabella esista
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS drops (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                    item TEXT NOT NULL,
                    quantity INTEGER NOT NULL,
                    price REAL NOT NULL,
                    total_value REAL NOT NULL,
                    client_pid INTEGER,
                    session_id INTEGER
                )
            ''')
            
            # Calcola valore totale
            total_value = quantity * price
            
            # Inserisci il drop
            cursor.execute('''
                INSERT INTO drops (item, quantity, price, total_value, client_pid, session_id)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (item, quantity, price, total_value, self.target_pid, self.session_id))
            
            conn.commit()
            conn.close()
            
        except Exception as e:
            print(f"❌ Errore nel salvare il drop: {e}")
    
    def start_scanning(self, scan_interval: float = 0.5):
        """
        Avvia la scansione continua della memoria
        
        Args:
            scan_interval: Intervallo tra scansioni in secondi
        """
        if not self.attach_to_process():
            print("\n💡 Suggerimento: Esegui questo script come Amministratore")
            print("   Clicca destro su loot_scanner.py -> Esegui come amministratore\n")
            return
        
        self.scanning = True
        print(f"\n🔍 Inizio scansione memoria GoonZu...")
        print(f"   Processo: PID {self.target_pid}")
        print(f"   Database: {self.db_path}")
        print(f"   Intervallo: {scan_interval}s")
        print("\n   Premi Ctrl+C per fermare la scansione\n")
        print("="*60)
        
        drop_count = 0
        
        try:
            while self.scanning:
                drops = self.scan_for_drops()
                
                for item, quantity, price in drops:
                    self.save_drop(item, quantity, price)
                    drop_count += 1
                    print(f"   [{drop_count}] {item} x{quantity} (valore: {quantity * price:.2f}M)")
                
                time.sleep(scan_interval)
                
        except KeyboardInterrupt:
            print("\n\n⏹️  Scansione interrotta dall'utente")
        except Exception as e:
            print(f"\n❌ Errore durante scansione: {e}")
        finally:
            self.stop_scanning()
    
    def stop_scanning(self):
        """Ferma la scansione e pulisce le risorse"""
        self.scanning = False
        
        if self.process_handle:
            try:
                win32api.CloseHandle(self.process_handle)
                print("🔒 Handle di processo chiuso")
            except:
                pass
        
        print(f"\n📊 Statistiche finali:")
        print(f"   Processo tracciato: PID {self.target_pid}")
        print(f"   Database: {self.db_path}")
        print("\n✅ Scansione terminata")


def main():
    """Funzione principale"""
    parser = argparse.ArgumentParser(
        description='GoonZu Farm Tracker - Loot Scanner',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Esempi:
  %(prog)s --list                    # Lista i processi GoonZu disponibili
  %(prog)s                           # Avvia scansione sul primo processo trovato
  %(prog)s --pid 12345               # Avvia scansione sul PID specificato
  %(prog)s --pid 12345 --db loot.db  # Usa database personalizzato
        """
    )
    
    parser.add_argument('--list', action='store_true',
                       help='Lista i processi GoonZu disponibili e esci')
    parser.add_argument('--pid', type=int,
                       help='PID del processo GoonZu da tracciare')
    parser.add_argument('--db', default='loot.db',
                       help='Percorso del database SQLite (default: loot.db)')
    parser.add_argument('--interval', type=float, default=0.5,
                       help='Intervallo tra scansioni in secondi (default: 0.5)')
    
    args = parser.parse_args()
    
    # Verifica dipendenze
    if not PSUTIL_AVAILABLE:
        print("❌ Errore: psutil non installato")
        print("   Installa con: pip install psutil")
        sys.exit(1)
    
    if not WIN32_AVAILABLE:
        print("❌ Errore: pywin32 non installato")
        print("   Installa con: pip install pywin32")
        sys.exit(1)
    
    # Modalità lista processi
    if args.list:
        list_processes()
        return
    
    # Verifica se siamo in modalità amministratore (solo warning)
    try:
        import ctypes
        is_admin = ctypes.windll.shell32.IsUserAnAdmin()
        if not is_admin:
            print("⚠️  ATTENZIONE: Non stai eseguendo come Amministratore")
            print("   Per leggere la memoria di GoonZu, è necessario eseguire come Amministratore")
            print("   Clicca destro su loot_scanner.py -> Esegui come amministratore\n")
            response = input("   Continuare comunque? (s/N): ")
            if response.lower() != 's':
                sys.exit(1)
    except:
        pass
    
    # Avvia scanner
    scanner = LootScanner(target_pid=args.pid, db_path=args.db)
    scanner.start_scanning(scan_interval=args.interval)


if __name__ == "__main__":
    main()