"# Proiect de Licență — Edge AI Surveillance

Sistem de supraveghere și alertare la intruși (decizia D3): camera observă și
anunță, nu deschide nicio ușă. Aplicația poate fi dezvoltată și testată pe
calculator fără Raspberry Pi. În modul de dezvoltare, FastAPI rulează local,
SQLite păstrează persoanele și evenimentele, iar endpointul de simulare
înlocuiește temporar camera și modelul AI.

## Backend local

Python 3.12 este folosit în mediul de dezvoltare curent, într-un mediu virtual
(`.venv`) din rădăcina proiectului. Din PowerShell:

```powershell
cd C:\Users\bianc\Desktop\Licenta
.\.venv\Scripts\Activate.ps1
cd backend
& "C:\Users\bianc\Desktop\Licenta\.venv\Scripts\python.exe" -m pip install -r requirements.txt
& "C:\Users\bianc\Desktop\Licenta\.venv\Scripts\python.exe" -m uvicorn main:app --reload --port 8000
```

Calea completă către `python.exe` din `.venv` nu este pedanterie: există un
`python.exe` în folderul home care câștigă în PATH, deci `Activate.ps1` singur
nu garantează că rulezi cu pachetele fixate în `requirements.txt`.

Instalarea pachetelor este necesară doar la prima rulare sau după modificarea
`requirements.txt`. După activare, promptul afișează `(.venv)`; activarea este
valabilă doar în fereastra curentă de terminal.

Serverul trebuie pornit din folderul `backend`, pentru că `main.py` se află
acolo și importurile sunt de forma `from app.config...`.

La prima pornire, baza SQLite se creează automat la `backend/data/access_control.sqlite3`, prin mecanismul de migrare versionat din `backend/app/config/database.py`. Pentru a folosi altă locație, setează `ACCESS_CONTROL_DB_PATH` înainte de pornire.

Documentația API este disponibilă la [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs).

## Primul administrator

Toate rutele de administrare cer rolul `ADMIN`, iar o bază nouă nu are niciun
administrator. Primul se creează local, o singură dată, din folderul `backend`:

```powershell
python tools\create_admin.py --name "Bianca" --email bianca@exemplu.ro
```

Parola este cerută interactiv (minim 8 caractere) și nu se dă ca argument, ca
să nu rămână în istoricul terminalului.

Apoi, în [/docs](http://127.0.0.1:8000/docs), apelează `POST /api/auth/login`
cu emailul și parola, copiază `access_token` din răspuns, apasă **Authorize**
sus în pagină și lipește-l. De acolo toate rutele protejate funcționează.

Rolurile: `ADMIN` administrează tot hub-ul; `APP_USER` se autentifică și vede
doar propriile evenimente; `MONITORED` nu are parolă, deci nu se poate
autentifica — este o persoană cunoscută de sistem, al cărei embedding servește
la a NU genera alertă când apare în zonele unde este așteptată.

### Variabile de mediu

| Variabilă | Rol | Obligatorie |
|---|---|---|
| `ACCESS_CONTROL_DB_PATH` | locația fișierului SQLite | nu |
| `ACCESS_CONTROL_JWT_SECRET` | secretul de semnare, minim 32 de bytes | **da în producție** |
| `ACCESS_CONTROL_CORS_ORIGINS` | originile permise, separate prin virgulă | nu |
| `ACCESS_CONTROL_MATCH_THRESHOLD` | pragul de similaritate (implicit 0.5) | nu |

Pragul implicit **nu este o valoare validată de securitate**. Trebuie calibrat
în Faza 3 pe date reale, cu rata de respingere falsă și de acceptare falsă
raportate.

În dezvoltare, dacă `ACCESS_CONTROL_JWT_SECRET` nu este setată, se generează
un secret o singură dată în `backend/data/jwt_secret.key` (exclus din Git).
Pe dispozitivul final, variabila trebuie setată explicit în configurația
serviciului.

## Teste automate

Din folderul `backend`, cu venv activat:

```powershell
& "C:\Users\bianc\Desktop\Licenta\.venv\Scripts\python.exe" -m unittest discover -s tests -v
```

78 de teste: mecanismul de migrare a schemei (inclusiv traducerea
vocabularului de dinainte de D3), CRUD persoane cu sincronizarea rolului,
unicitatea emailului, paginarea jurnalului, hashing-ul parolelor,
autentificarea (inclusiv imposibilitatea de login pentru `MONITORED` și
limitarea încercărilor), aplicarea RBAC pe fiecare rută, camerele cu validarea
permisiunilor, clasificarea detecției (prag, zone permise, fail-loud, politica
de fotografii), ștergerea în masă a jurnalului cu gărzile ei, și coerența
jurnalului.

## Contractul de detecție

Camerele se înregistrează prin `POST /api/cameras/`, iar fiecare `camera_id`
din `allowed_cameras` trebuie să existe în hub — altfel înrolarea este
respinsă cu 422. O greșeală de scriere nu mai poate produce o permisiune care
nu se potrivește niciodată. După D3, `allowed_cameras` înseamnă „zonele în
care persoana este așteptată", nu „ușile pe care le poate deschide".

`POST /api/detection/evaluate` este contractul: primește `camera_id` și un
`embedding`, verifică întâi camera și apoi identitatea, scrie evenimentul în
jurnal și returnează clasificarea împreună cu scorul și pragul.

```json
{
  "camera_id": "cam_entrance",
  "embedding": [1.0, 0.0, 0.0, 0.0]
}
```

Răspunsul este mereu `200`, inclusiv la alertă: alerta este un rezultat valid
al operației, nu o eroare a cererii. Rezultatul are două niveluri separate:

| `reason` (jurnal, statistici) | `outcome` (ce face sistemul) |
|---|---|
| `KNOWN` | `KNOWN` — nimic |
| `INTRUDER` | `ALERT` — alertă de securitate, fotografia se păstrează |
| `UNEXPECTED_ZONE` | `ALERT` — persoană identificată, în zonă neașteptată |
| `EMPTY_WHITELIST` | `ALERT` — nimeni înrolat, deci orice față e necunoscută |
| `CAMERA_UNKNOWN` | `FAULT` — eroare de configurare |
| `CAMERA_DISABLED` | `FAULT` — cameră oprită intenționat |
| `DEGRADED` | `FAULT` — sistemul nu a putut evalua |

Separarea e esențială: alerta de intrus și alerta de defect au destinatari
diferiți. Dacă ar fi contopite, o cameră stricată ar produce notificări care
arată ca tentative de intrare, iar utilizatorul ar învăța să le ignore.

Comportamentul este *fail-loud*: orice situație neprevăzută produce `FAULT`
cu motivul `DEGRADED`, niciodată o excepție și niciodată tăcere. Până la D3
sistemul comanda o yală și corect era *fail-closed*; într-un sistem de
supraveghere, tăcerea este varianta periculoasă. Bucla de recunoaștere de pe
Raspberry Pi va apela `DetectionService.evaluate()` direct, în proces, nu
prin HTTP.

Similaritatea cosinus din `backend/app/services/matching.py` este
implementarea de referință, în Python pur. **Nu o optimiza**: este baseline-ul
față de care se compară nucleul ARM NEON din Faza 4.

## Coerența jurnalului

Un eveniment ori numește o persoană, ori nu poate numi niciuna. `KNOWN` și
`UNEXPECTED_ZONE` cer `user_id`; restul motivelor îl refuză. Regula trăiește
în `describe_identity_conflict` din `backend/app/schemas/detection_schema.py`,
ca serviciul de detecție și ruta manuală să nu se poată despărți.

`user_name` trimis de client este ignorat: numele este derivat din persoana
referită. Un rând care ar numi altcineva decât persoana pe care o indică ar
arăta ca o probă, fiind fals.

## Ștergerea în masă și retenția

`DELETE /api/logs/` șterge mai multe evenimente dintr-o dată, cu filtre
opționale pe `camera_id`, `status` și `before`. Cere explicit `confirm=true`,
iar garda stă în stratul service, nu în router, ca nicio altă cale de apel să
nu o poată ocoli. Cu `before`, exact această metodă este mecanismul politicii
de retenție cerută de decizia D2 (ștergere automată după 7-30 de zile).

## Testare fără hardware, prin simulare

După autorizare în `/docs`, adaugă o persoană prin `POST /api/whitelist/`,
apoi simulează un eveniment cu o persoană cunoscută:

```json
{
  "expected": true,
  "user_id": "ID-ul-persoanei",
  "camera_id": "cam_entrance"
}
```

Trimite corpul la `POST /api/simulation/detection` (necesită rol `ADMIN`).
Pentru simularea unui intrus, folosește `{"expected": false}`. Evenimentele
sunt păstrate în SQLite și apar în `GET /api/logs/`.

Endpointul de simulare **nu este recunoaștere facială**: primește `expected`
ca boolean de la client și îl crede, nu verifică `allowed_cameras` și nu
compară niciun embedding. Rămâne util ca frontendul să poată fi construit
înainte să existe hardware, dar e restricționat la `ADMIN`, pentru că pe un
sistem funcțional orice client care l-ar putea apela ar putea falsifica
jurnalul de audit.

## Frontend

Aplicația Expo (React Native + TypeScript, cu `expo-router` și React Native
Paper) este în `frontend/`. Rulează din același cod pe iOS, Android și în
browser. Pornire:

```powershell
cd C:\Users\bianc\Desktop\Licenta\frontend
npx expo start --web
```

Ecrane existente: autentificare, jurnalul de evenimente și profilul cu rolul
și deconectarea. Token-ul se păstrează în `expo-secure-store` pe telefon și în
`localStorage` pe web.

Pe telefon, prin Expo Go, `127.0.0.1` este **telefonul**, nu laptopul. Pune
adresa laptopului din rețea în `frontend/.env`:

```
EXPO_PUBLIC_API_URL=http://192.168.1.X:8000
```

și pornește backendul cu `--host 0.0.0.0`, altfel uvicorn ascultă doar local.

## Date și secrete

Folderul `backend/data/` este exclus din Git: conține baza SQLite locală și,
în dezvoltare, `jwt_secret.key`. Fișierele versiunii Firebase au fost șterse
din proiect.

Nu adăuga credențiale, parole, imagini faciale sau embedding-uri reale în
repository. Vectorii biometrici nu sunt returnați de API: răspunsurile conțin
doar `has_embedding: true/false`."
