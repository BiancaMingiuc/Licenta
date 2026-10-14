# Context tehnic — Proiect de Licență Edge AI

Acest document rezumă starea proiectului la 13 octombrie 2026, pentru a putea relua lucrul fără să fie nevoie de reconstruirea contextului din conversații. Descrie ce există în cod, ce a fost verificat și ce rămâne de făcut. Nu include și nu trebuie completat cu valorile din fișierul de credențiale Firebase.

## Scopul proiectului

Proiectul urmărește un sistem de recunoaștere facială și control al accesului, cu țintă de rulare offline pe Raspberry Pi 4 Model B cu 2 GB RAM. Contribuția științifică planificată este măsurarea inferenței AI de bază și apoi compararea ei cu o implementare optimizată hardware în C/C++ pentru ARM NEON.

Ordinea de lucru stabilită:

1. Backend și bază de date.
2. Aplicație mobilă React Native/Expo.
3. Pipeline video, model AI de bază, senzori și măsurători de referință.
4. Optimizări C/C++: IM2COL în blocuri, cache blocking, micro-kernel ARM NEON 8 × 8 și fuziunea Batch Normalization/ReLU în convoluție.

## Decizie de arhitectură: Edge AI, cloud și experiența aplicației

S-a discutat posibilitatea de a trimite imaginile camerei într-un cloud pentru recunoașterea facială, astfel încât Raspberry Pi să nu mai încarce modelul AI. Această variantă este posibilă, dar reduce memoria necesară doar pentru model/inferență: Pi-ul continuă să gestioneze camera, cadrele, compresia și conexiunea de rețea. În plus, fiecare decizie depinde de internet, poate avea latență mai mare și trimite date biometrice sensibile în afara dispozitivului. O întrerupere de internet poate opri identificarea și decizia de acces.

Pentru obiectivul științific al lucrării, inferența în cloud nu este arhitectura principală recomandată: ar elimina demonstrația optimizării inferenței pe Raspberry Pi (memorie, latență, FPS și ARM NEON). Ar putea fi menționată drept alternativă sau comparație, nu drept calea normală de procesare.

Arhitectura recomandată pentru produsul demonstrativ este hibridă:

1. Raspberry Pi captează cadrul, detectează/recunoaște fața și decide local dacă accesul este permis.
2. Lista utilizatorilor autorizați, embeddings și istoricul evenimentelor sunt păstrate local pe Pi; funcțiile de securitate continuă fără internet.
3. La înrolarea unei persoane, aplicația trimite datele către backendul FastAPI al Pi-ului, iar Pi-ul generează embedding-ul și îl salvează local.
4. Pentru administrare de acasă, telefonul accesează API-ul prin rețeaua locală. Pentru acces din afara casei, se recomandă un VPN către rețeaua de acasă, nu expunerea directă a API-ului pe internet.
5. Pentru notificări când aplicația este închisă și utilizatoarea este plecată, Pi-ul poate trimite o alertă minimală prin serviciile push Apple/Google. Aceste servicii primesc alerta, nu baza de utilizatori, embedding-urile sau imaginile, dacă integrarea este proiectată astfel.

Notificările push de la distanță necesită ca Pi-ul și telefonul să aibă acces la internet și depind de infrastructura Apple/Google; prin urmare, soluția nu este „zero-cloud” în sens absolut. Dacă internetul cade, Pi-ul poate continua recunoașterea și salvarea locală a evenimentelor, însă notificarea nu ajunge la telefon până la revenirea conexiunii. Formularea tehnică potrivită pentru proiect este: **inferență și control al accesului Edge AI, date păstrate local, administrare la distanță securizată și notificări push prin serviciile platformei**.

## Structura proiectului observată

```text
Licenta/
├── backend/
│   ├── main.py
│   ├── database.py
│   └── app/
│       ├── config/firebase.py
│       ├── repositories/
│       │   ├── user_repo.py
│       │   └── log_repo.py
│       ├── routers/
│       │   ├── user_router.py
│       │   └── log_router.py
│       ├── schemas/
│       │   ├── user_schema.py
│       │   └── log_schema.py
│       └── services/
│           ├── user_service.py
│           └── log_service.py
├── frontend/
│   ├── App.tsx
│   ├── app.json
│   ├── index.ts
│   ├── package.json
│   └── package-lock.json
├── .gitignore
└── README.md
```

## Backend — implementat pentru dezvoltare locală fără hardware

Backendul folosește FastAPI. `backend/main.py` creează aplicația, configurează CORS și înregistrează routerele pentru whitelist și loguri. Ruta rădăcină `GET /` returnează un mesaj de confirmare. Documentația generată automat de FastAPI este disponibilă la `/docs`, iar schema OpenAPI la `/openapi.json`.

Codul este împărțit pe straturi:

- **Routers** (`backend/app/routers/`) declară rutele HTTP și validează cererile cu schemele Pydantic.
- **Services** (`backend/app/services/`) aplică logica aplicației și transformă situațiile de tip „nu există” sau „cerere goală” în răspunsuri HTTP.
- **Repositories** (`backend/app/repositories/`) citesc și scriu datele în SQLite.
- **Schemas** (`backend/app/schemas/`) descriu și validează datele de intrare/ieșire.
- **Config** (`backend/app/config/database.py`) inițializează schema SQLite și deschide conexiuni cu cheile externe activate.

### API whitelist / utilizatori

Prefixul rutelor este `/api/whitelist/`:

| Metodă | Rută | Comportament |
|---|---|---|
| GET | `/api/whitelist/?hub_id=HUB_001` | Listează utilizatorii filtrând după hub; `hub_id` are implicit valoarea `HUB_001`. |
| GET | `/api/whitelist/{doc_id}` | Returnează un utilizator și logurile asociate prin `user_id`; răspunde cu 404 dacă utilizatorul lipsește. |
| POST | `/api/whitelist/` | Creează un utilizator în tabela locală `users`. |
| PUT | `/api/whitelist/{doc_id}` | Actualizează câmpurile trimise; corpul fără câmpuri actualizabile produce 400, iar ID-ul inexistent produce 404. |
| DELETE | `/api/whitelist/{doc_id}` | Șterge utilizatorul; ID-ul inexistent produce 404. |

Schema utilizatorului definește câmpurile `hub_id`, `name`, `role`, `has_app_access`, `email`, `allowed_cameras` și `embedding`. Rolurile permise sunt `ADMIN`, `APP_USER` și `PHYSICAL_ONLY`. Valorile implicite includ `hub_id="HUB_001"`, rolul `PHYSICAL_ONLY` și camera `cam_intrare`.

La creare și la actualizarea rolului, service-ul sincronizează `has_app_access`: este adevărat pentru `ADMIN` și `APP_USER`, fals pentru `PHYSICAL_ONLY`. Detaliul utilizatorului adaugă și lista de loguri asociate.

### API loguri de acces

Prefixul rutelor este `/api/logs/`:

| Metodă | Rută | Comportament |
|---|---|---|
| GET | `/api/logs/?hub_id=HUB_001&camera_id=cam_intrare` | Listează logurile pentru hub și, opțional, filtrează după cameră. Rezultatele sunt sortate descrescător după timestamp. |
| POST | `/api/logs/` | Creează un log în tabela locală `logs`, cu timestamp UTC generat de backend. |
| DELETE | `/api/logs/{doc_id}` | Șterge logul; ID-ul inexistent produce 404. |

Schema logului definește `hub_id`, `camera_id`, `user_id`, `user_name` și `status`. Stările permise la creare sunt `GRANTED` și `DENIED`; valorile implicite reprezintă un acces refuzat de la camera `cam_intrare` pentru un utilizator necunoscut.

### SQLite local și simulare fără hardware

Repository-urile active folosesc SQLite, nu Firestore. Schema este inițializată la pornirea FastAPI; baza implicită este `backend/data/access_control.sqlite3`, iar locația poate fi schimbată prin variabila `ACCESS_CONTROL_DB_PATH`. Directorul implicit este exclus din Git. Tabelele `users` și `logs` au indecși pentru hub/cameră/timestamp și utilizator; ștergerea unui utilizator păstrează logurile și setează `user_id` la `NULL`.

`POST /api/simulation/detection` creează un eveniment simulat autorizat sau refuzat, fără cameră, senzor sau model AI. Pentru eveniment autorizat este necesar un `user_id` existent. Endpointul este destinat dezvoltării, nu constituie recunoaștere sau autorizare reală.

Fișierul `backend/app/config/firebase.py`, vechiul `backend/database.py` și `backend/firebase_credentials.json` sunt artefacte ale variantei Firestore anterioare și nu sunt folosite de rutele active. Credențialele rămân ignorate în Git. Nu copia secretele în cod, documentație, mesaje de eroare sau repository.

SQLite permite dezvoltarea locală pe calculator și poate rula ulterior pe Pi, dar datele nu se sincronizează automat cu Firestore sau cu telefonul. Baza locală singură nu oferă acces remote, push notifications ori o aplicație frontend funcțională.

### Fișier legacy

`backend/database.py` conține o implementare anterioară, separată, cu funcții directe pentru whitelist și loguri. `backend/main.py` actual folosește arhitectura `backend/app/...`, iar acest fișier legacy nu apare în lanțul de import al aplicației. Evită să întreții două implementări paralele; înainte de ștergerea sau reutilizarea lui, verifică dacă există alte referințe.

### Pornirea backendului

`main.py` se află în `backend`. Pornește serverul din folderul `backend`:

```powershell
cd C:\Users\bianc\Desktop\Licenta\backend
py -3.12 -m uvicorn main:app --reload --port 8000
```

Alternativ, din rădăcina proiectului:

```powershell
py -3.12 -m uvicorn main:app --app-dir backend --reload --port 8000
```

Comanda `uvicorn main:app` executată din rădăcină fără `--app-dir backend` nu găsește modulul `main`. Python 3.12 este folosit în mediul local. Pachetele backendului sunt declarate în `backend/requirements.txt`.

## Frontend — instalat, interfața încă neimplementată

Frontendul este un proiect Expo cu React Native, React și TypeScript strict. `frontend/package.json` declară Expo, React Native, suport web și `expo-image-picker`, precum și scripturile:

```powershell
cd C:\Users\bianc\Desktop\Licenta\frontend
npm run start
npm run web
```

`frontend/App.tsx` afișează încă ecranul inițial Expo („Open up App.tsx to start working on your app!”). Nu există încă dashboard, ecrane pentru whitelist/loguri sau apeluri către API. Pachetul `expo-image-picker` este instalat, dar nu este utilizat în interfața actuală.

În verificarea făcută, `npm ls --depth=0` a raportat dependențele instalate, `npm exec -- tsc --noEmit` s-a terminat fără erori, iar `npm exec -- expo config --type public` a încărcat configurația pentru Android, iOS și Web.

Pentru testarea de pe un telefon, adresa API nu va fi `127.0.0.1` de pe telefon; trebuie configurată adresa IP locală a calculatorului și permis accesul în firewall. Această configurare nu este încă implementată.

## Git și fișiere locale

- Rădăcina `.gitignore` exclude `backend/firebase_credentials.json`.
- `frontend/.gitignore` exclude `node_modules`, artefactele Expo și fișiere locale de environment.
- Fișierele `.pyc`/`__pycache__` au apărut în statusul Git ca neignorate. Ar trebui adăugate reguli Python în `.gitignore` înainte de includerea backendului în commit.
- `README.md` conține momentan doar titlul proiectului.
- Existența fișierelor în director nu înseamnă că sunt deja în Git; verifică `git status` și fă commit doar după ce ai exclus credențialele.

## Stadiul pe faze

| Fază | Stare | Detalii |
|---|---|---|
| 1. Backend și DB | Backend local pentru dezvoltare implementat | FastAPI, CRUD whitelist, loguri SQLite locale și endpoint de simulare; teste automate pentru CRUD/simulare. Mai trebuie validat pe Raspberry Pi și cu test offline/restart pe mediul țintă. |
| 2. Frontend Expo | Proiect inițializat, UI neimplementată | Pachetele sunt instalate și type-check/configurația trec; ecranul curent este placeholder și nu consumă backendul. |
| 3. AI și hardware | Neîncepută | Nu există încă pipeline OpenCV/Tiny-ResNet, cosine similarity, GPIO, integrare senzori sau baseline măsurat. |
| 4. Optimizări C/C++ | Neîncepută | Nu există încă extensie Cython/C++, IM2COL pe blocuri, cache blocking, NEON sau layer fusion. |

## Plan: persistență locală și operare offline

### Decizia de arhitectură

Pentru cerința strictă „zero-cloud”, Raspberry Pi-ul trebuie să poată citi și scrie datele de acces fără Firebase sau internet. Decizia pentru acest proiect este SQLite local ca sursă principală de adevăr. SQLite face parte din biblioteca standard Python (`sqlite3`), nu cere un server separat și este potrivit pentru dimensiunea redusă a bazei de date a proiectului. Un prim backend local a fost implementat și poate fi dezvoltat pe calculator înainte să existe hardware.

Firebase/Firestore nu trebuie apelat în fluxul normal de verificare a accesului. O sincronizare opțională cu un serviciu la distanță ar fi o funcționalitate separată, ulterioară, și ar contrazice o interpretare strictă zero-cloud dacă devine necesară pentru funcționare.

### Etapa 1 — stabilește datele păstrate local

Definește schema SQLite pentru:

- **users**: ID stabil, `hub_id`, nume, rol, acces la aplicație, email, camere permise, embedding-ul facial și metadatele modelului (versiune și dimensiune).
- **logs**: ID, `hub_id`, cameră, utilizator (poate lipsi pentru necunoscut), nume, rezultat (`GRANTED`/`DENIED`) și timestamp UTC.

Păstrează embedding-urile într-un format binar compact sau într-un format serializat cu versiunea/dimensiunea explicită; alege reprezentarea după ce este stabilit formatul numeric folosit de model. Nu salva imaginile faciale brute decât dacă există o cerință clară și măsuri adecvate de consimțământ și protecție.

Adaugă indecși pentru interogările folosite, cel puțin după `hub_id`, `user_id` și timestamp-ul logurilor. Activează cheile externe și definește clar ce se întâmplă cu logurile la ștergerea unui utilizator (de exemplu, păstrarea istoricului cu `user_id` nul sau un identificator istoric).

### Etapa 2 — separă accesul la date de Firestore

Păstrează contractele routerelor și serviciilor, dar înlocuiește repository-urile Firestore cu repository-uri SQLite. Configurează calea bazei de date printr-o setare de aplicație, cu o locație persistentă pe Raspberry Pi; nu o ține într-un director temporar și nu presupune că directorul curent al procesului este rădăcina proiectului.

Inițializează schema printr-o migrare explicită la pornire sau printr-o comandă administrativă. Folosește tranzacții pentru operațiile care trebuie să fie atomice. Nu schimba API-ul frontendului fără motiv: rutele curente pentru whitelist și loguri pot continua să existe, deși backendul își schimbă implementarea de persistență.

### Etapa 3 — migrează datele existente o singură dată

Dacă există utilizatori/loguri în Firestore care trebuie păstrați, scrie un instrument separat de import, rulat intenționat cât timp există conexiune. Importă și verifică numărul de înregistrări și câmpurile obligatorii, păstrează ID-urile relevante dacă nu produc coliziuni și evită duplicatele la o rerulare. După import, aplicația de pe Pi trebuie să funcționeze fără inițializarea Firebase.

Nu pune credențialele Firebase pe dispozitiv pentru execuția offline. Păstrează fișierul secret exclus din Git și nu include conținutul lui în loguri sau documentație.

### Etapa 4 — verifică CRUD-ul și funcționarea fără rețea

Adaugă teste automate pentru:

1. Inițializarea bazei și migrarea unei baze goale.
2. Crearea, listarea, citirea, actualizarea și ștergerea utilizatorilor.
3. Crearea/listarea/ștergerea logurilor și filtrele pentru hub/cameră/utilizator.
4. Validarea rolurilor și stărilor, răspunsurile 404/400 și persistarea după repornirea procesului.
5. Două cereri concurente și înregistrarea atomică a rezultatului de acces.

Testul de acceptanță offline: oprește backendul, dezactivează rețeaua, pornește-l din nou pe dispozitiv și demonstrează că API-ul poate adăuga/citi utilizatori și scrie/citi loguri. Repornește serviciul și verifică faptul că datele încă există.

### Etapa 5 — conectează recunoașterea facială la datele locale

În faza AI, încarcă embeddings autorizate din SQLite (sau dintr-un cache reîmprospătat din SQLite) și efectuează compararea cosine similarity local. Calibrează și documentează pragul folosind date de test; nu presupune că orice prag implicit este suficient pentru securitatea accesului.

Scrie rezultatul fiecărei tentative în logul SQLite, inclusiv pentru necunoscut/refuzat. Deschide releul numai după o decizie locală validă și stabilește un comportament fail-closed când baza, camera sau modelul nu sunt disponibile.

### Etapa 6 — backup și operare

Documentează locația bazei, backup-ul, restaurarea și migrarea versiunilor de schemă. Folosește permisiuni de sistem de operare restrictive pentru fișierul SQLite și backup-uri. Verifică spațiul disponibil și comportamentul la oprire neașteptată. WAL poate fi evaluat pentru acces concurent, dar trebuie folosit împreună cu backup corect (nu copia doar fișierul principal cât timp baza este activă).

### Sincronizarea cu Firebase — opțională, nu parte din MVP offline

Dacă ulterior se cere replicarea în cloud, trateaz-o ca un strat separat: coadă/outbox locală cu ID-uri de operații stabile, retry cu backoff, idempotency și politică explicită de rezolvare a conflictelor. Accesul, decizia facială și logarea locală nu trebuie să aștepte sincronizarea. Dacă obiectivul rămâne strict zero-cloud, nu implementa acest strat.

## Următorii pași recomandați

1. Confirmă SQLite local ca sursă de adevăr pentru utilizatori și loguri pe Raspberry Pi.
2. Migrarea Firestore nu este încă implementată; adaug-o numai dacă există date reale de păstrat.
3. Construiește ecranele Expo pentru dashboard, whitelist și loguri; conectează-le la API și configurează URL-ul de bază separat de codul UI.
4. Extinde simularea doar cât este necesar pentru dezvoltare și teste; păstreaz-o clar separată de API-ul și deciziile reale ale camerei.
5. Validează backendul pe Raspberry Pi când hardware-ul devine disponibil și demonstrează persistența după restart și funcționarea fără internet.
6. Abia după ce fazele 1 și 2 funcționează end-to-end, începe pipeline-ul AI de bază și colectează măsurători de referință pentru RAM, latență și FPS înaintea optimizărilor.
