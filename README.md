"# Proiect de Licență — Edge AI Access Control

Aplicația poate fi dezvoltată și testată pe calculator fără Raspberry Pi. În modul de dezvoltare, FastAPI rulează local, SQLite păstrează utilizatorii și evenimentele, iar endpointul de simulare înlocuiește temporar camera și senzorii.

## Backend local

Python 3.12 este folosit în mediul de dezvoltare curent, într-un mediu virtual
(`.venv`) din rădăcina proiectului. Din PowerShell:

```powershell
cd C:\Users\bianc\Desktop\Licenta
.\.venv\Scripts\Activate.ps1
py -3.12 -m pip install -r backend\requirements.txt
cd backend
python -m uvicorn main:app --reload --port 8000
```

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
doar propriile evenimente; `PHYSICAL_ONLY` nu are parolă, deci nu se poate
autentifica — are doar acces fizic la ușă.

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
python -m unittest discover -s tests -v
```

60 de teste: mecanismul de migrare a schemei, CRUD utilizatori cu
sincronizarea rolului, unicitatea emailului, paginarea logurilor, hashing-ul
parolelor, autentificarea (inclusiv imposibilitatea de login pentru
`PHYSICAL_ONLY` și limitarea încercărilor), aplicarea RBAC pe fiecare rută,
camerele cu validarea permisiunilor, și decizia de acces (prag, permisiune per
cameră, fail-closed, politica de fotografii).

## Decizia de acces

Camerele se înregistrează prin `POST /api/cameras/`, iar fiecare `camera_id`
din `allowed_cameras` trebuie să existe în hub — altfel înrolarea este
respinsă cu 422. O greșeală de scriere nu mai poate produce o permisiune care
nu se potrivește niciodată.

`POST /api/access/evaluate` este contractul deciziei: primește `camera_id` și
un `embedding`, verifică întâi camera și apoi identitatea, scrie evenimentul în
jurnal și returnează decizia împreună cu scorul și pragul.

```json
{
  "camera_id": "cam_intrare",
  "embedding": [1.0, 0.0, 0.0, 0.0]
}
```

Răspunsul este mereu `200`, inclusiv la refuz: refuzul este un rezultat valid,
nu o eroare a cererii. Motivul explică refuzul (`UNKNOWN_FACE`,
`CAMERA_NOT_ALLOWED`, `CAMERA_DISABLED`, `EMPTY_WHITELIST`, …).

Comportamentul este *fail-closed*: orice situație neprevăzută produce `DENIED`,
niciodată o excepție. Bucla de recunoaștere de pe Raspberry Pi va apela
`AccessService.evaluate()` direct, în proces, nu prin HTTP.

Similaritatea cosinus din `backend/app/services/matching.py` este
implementarea de referință, în Python pur. **Nu o optimiza**: este baseline-ul
față de care se compară nucleul ARM NEON din Faza 4.

## Testare fără hardware, prin simulare

După autorizare în `/docs`, adaugă un utilizator prin `POST /api/whitelist/`,
apoi simulează un eveniment autorizat:

```json
{
  "authorized": true,
  "user_id": "ID-ul-utilizatorului",
  "camera_id": "cam_intrare"
}
```

Trimite corpul la `POST /api/simulation/detection` (necesită rol `ADMIN`). Pentru simularea unei persoane neautorizate, folosește `{"authorized": false}`. Evenimentele sunt păstrate în SQLite și apar în `GET /api/logs/`.

Endpointul de simulare este pentru dezvoltare și nu înlocuiește recunoașterea facială sau logica de autorizare finală.

## Frontend

Frontendul Expo este în `frontend/`. Pornește-l cu:

```powershell
cd C:\Users\bianc\Desktop\Licenta\frontend
npm run start
```

Interfața încă folosește ecranul inițial Expo; conectarea ei la rutele backendului este următoarea parte de implementat.

## Date și secrete

Folderul `backend/data/` este exclus din Git: conține baza SQLite locală și,
în dezvoltare, `jwt_secret.key`. Fișierele versiunii Firebase au fost șterse
din proiect.

Nu adăuga credențiale, parole, imagini faciale sau embedding-uri reale în
repository. Vectorii biometrici nu sunt returnați de API: răspunsurile conțin
doar `has_embedding: true/false`."
