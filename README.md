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

## Testare fără hardware

Din folderul `backend`, cu venv activat:

```powershell
python -m unittest discover -s tests -v
```

7 teste: CRUD utilizatori cu sincronizarea rolului, simulare autorizată și
refuzată, păstrarea istoricului la ștergerea unui utilizator, și patru teste
pentru mecanismul de migrare a schemei.

Adaugă un utilizator prin `POST /api/whitelist/`, apoi simulează un eveniment autorizat:

```json
{
  "authorized": true,
  "user_id": "ID-ul-utilizatorului",
  "camera_id": "cam_intrare"
}
```

Trimite corpul la `POST /api/simulation/detection`. Pentru simularea unei persoane neautorizate, folosește `{"authorized": false}`. Evenimentele sunt păstrate în SQLite și apar în `GET /api/logs/`.

Endpointul de simulare este pentru dezvoltare și nu înlocuiește recunoașterea facială sau logica de autorizare finală.

## Frontend

Frontendul Expo este în `frontend/`. Pornește-l cu:

```powershell
cd C:\Users\bianc\Desktop\Licenta\frontend
npm run start
```

Interfața încă folosește ecranul inițial Expo; conectarea ei la rutele backendului este următoarea parte de implementat.

## Date și secrete

Baza SQLite locală și fișierul `backend/firebase_credentials.json` sunt excluse din Git. Nu adăuga credențiale, imagini faciale sau embedding-uri reale în repository."
