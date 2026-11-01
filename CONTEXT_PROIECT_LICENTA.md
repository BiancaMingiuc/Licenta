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
5. Aplicația mobilă folosește locația telefonului doar local, ca să stabilească dacă utilizatoarea este în proximitatea camerei. Sunetul și vibrația sunt actuatori de notificare: lângă cameră se preferă notificare vizuală și vibrație, fără sunet; la distanță se poate folosi și sunet. Acest mecanism nu influențează niciodată decizia de deschidere a ușii.

Pentru obiectivul strict „zero-cloud”, notificările nu folosesc Apple Push Notification
Service, Firebase Cloud Messaging sau alt serviciu extern în MVP. Când aplicația este
conectată prin VPN, ea poate primi evenimentele de la backendul local și poate
declanșa local sunetul sau vibrația. Dacă aplicația este complet închisă sau telefonul
nu are conexiune VPN, notificarea instant fără un serviciu push extern nu este garantată;
Pi-ul continuă însă să recunoască fețele, să decidă accesul și să scrie logurile local.
Formularea tehnică pentru proiect este: **inferență, control al accesului, stocare și
procesare locală Edge AI; administrare prin VPN; notificări locale controlate de
proximitatea telefonului**.

### Decizie confirmată: senzori și actuatori ai aplicației mobile

Locația este o sursă de context/senzor, nu un actuator. Motorul de vibrație și
redarea sunetului sunt actuatori ai telefonului. În Faza 3, aplicația mobilă va:

1. obține locația cu permisiunea utilizatoarei;
2. calcula local distanța față de locația configurată a camerei;
3. folosi o rază configurabilă și o politică de rezervă când locația nu este
   disponibilă;
4. activa vibrația fără sunet când telefonul este în proximitatea camerei;
5. permite sunetul împreună cu vibrația când telefonul este la distanță;
6. nu trimite locația către cloud și, în mod normal, nu o salvează în SQLite.

GPS-ul poate fi imprecis în interior, deci raza trebuie calibrată experimental.
Pentru un comportament sigur și predictibil, locația necunoscută va permite
sunetul, nu îl va suprima. Proximitatea telefonului controlează doar prezentarea
notificării și nu acordă, revocă sau schimbă drepturi de acces.

## Decizii confirmate: acces remote prin VPN și fotografii doar la acces refuzat

Luate la 18 octombrie 2026. Acestea sunt **decizii închise**, nu opțiuni
deschise; se implementează în Faza 3. O unealtă care găsește contradicții
între ele și text mai vechi din acest document trebuie să le respecte pe
acestea.

## D3 — Sistem de supraveghere și alertare, FĂRĂ actuator de încuietoare

Luată la 27 octombrie 2026. **Această decizie anulează orice formulare din
acest document care presupune o încuietoare electrică, un releu care comandă
o yală, sau o „decizie de deschidere a ușii".** Textul mai vechi de la D1/D2
și din secțiunile de arhitectură folosește încă vocabularul de control al
accesului; unde contrazice D3, D3 are prioritate.

Decizia: camera are **exclusiv** rol de supraveghere și de înștiințare în caz
de intrus. Nu există yală electromagnetică, nu există releu care deschide o
ușă, nu există acces fizic acordat de sistem. Lista de persoane cunoscute nu
mai este o listă de persoane cu drept de intrare, ci o listă de persoane
**așteptate**, folosită pentru a decide dacă o detecție merită o alertă.

### Consecința cea mai importantă: semantica de siguranță se inversează

În modelul cu încuietoare, comportamentul corect la eroare era **fail-closed**:
dacă baza de date, camera sau modelul nu răspund, ușa rămâne închisă. Tăcerea
era varianta sigură.

În modelul de supraveghere, **tăcerea este varianta periculoasă**. Dacă
pipeline-ul cade, nimeni nu este anunțat, iar un intrus trece neobservat.
Comportamentul corect devine **fail-loud**: la eroare se emite o alertă.

Prin urmare `DetectionService.evaluate()` (redenumit din `AccessService` odată
cu D3) își păstrează proprietatea de a nu
ridica niciodată excepții, dar rezultatul implicit la eroare se schimbă de la
„refuz" la „alertă de sistem". Alerta de defect trebuie să fie **distinctă**
de alerta de intrus (`DEGRADED` vs `INTRUDER`), altfel o cameră defectă produce
alerte care par tentative de intrare.

### Vocabular (de aplicat în schemă, servicii și teste)

| Vechi | Nou | Semnificație |
|---|---|---|
| `GRANTED` | `KNOWN` | persoană așteptată, pe o cameră unde este așteptată |
| `DENIED` + `UNKNOWN_FACE` | `INTRUDER` | față nerecunoscută — alertă cu fotografie |
| `DENIED` + `CAMERA_NOT_ALLOWED` | `UNEXPECTED_ZONE` | persoană **identificată**, pe o cameră unde nu este așteptată — rămâne semnal valid de supraveghere |
| `DENIED` + `INTERNAL_ERROR` | `DEGRADED` | sistemul nu a putut evalua — alertă de defect, nu de intrus |

`allowed_cameras` nu se redenumește în schemă, dar își schimbă sensul: din
„camere pe care această persoană are drept să deschidă" în „zone în care
această persoană este așteptată". Designul multi-cameră își păstrează astfel
valoarea integral.

### Scop nou, care nu exista în modelul cu ușă

**Agregarea evenimentelor este obligatorie.** O ușă se deschide o singură dată
per prezentare. O cameră procesează continuu: o persoană care stă 30 de secunde
în cadru, la 10 FPS, generează 300 de detecții identice. Fără agregare, jurnalul
devine inutilizabil și notificările nefolosibile.

Cerință: detecțiile consecutive ale aceleiași identități (sau ale aceleiași
persoane necunoscute) pe aceeași cameră se grupează într-un **singur eveniment**
cu interval de început/sfârșit și o fotografie reprezentativă, folosind o
fereastră de inactivitate configurabilă. Se implementează în Faza 3, în stratul
service, nu în bucla de cadre.

**Notificarea devine actuatorul principal.** În modelul cu yală, lanțul se
termina la releu, iar notificarea era opțională. Acum lanțul se termină la
telefon. Prin urmare notificările locale din aplicația mobilă (fără cloud,
conform D1) nu mai sunt o funcționalitate secundară, ci livrabilul final al
sistemului.

**Fotografia devine produsul, nu un artefact secundar.** D2 rămâne valabilă în
conținut (imagine doar pentru persoane necunoscute, nu pentru cele așteptate),
dar `snapshot_path` devine obligatoriu pentru evenimentele de tip `INTRUDER`,
nu opțional.

### Impactul pe argumentul științific

Nucleul Fazei 4 este **neatins**: pipeline-ul de inferență, extragerea
embedding-ului și potrivirea cosinus sunt identice. Optimizarea NEON nu depinde
de existența unei încuietori.

Se schimbă însă **motivația metricii de latență**, și acest lucru trebuie
reformulat în lucrare. Vechiul argument („o persoană așteaptă în fața ușii,
deci latența e vizibilă") dispare. Noul argument este mai bun și trebuie scris
explicit: într-un sistem de supraveghere, cadrele sosesc la rată fixă, deci
latența per cadru determină **rata maximă susținută de procesare**. Dacă
latența depășește intervalul dintre cadre, cadrele se pierd, iar un intrus
poate traversa zona neanalizat. Latența nu mai este o problemă de confort, ci
de **acoperire a detecției**.

Două câștiguri colaterale pentru lucrare: procesarea continuă 24/7 este o
cerință mai dură decât evaluarea la cerere, deci metricile de FPS și de memorie
devin mai relevante; iar supravegherea implică mai multe fețe simultan în cadru,
ceea ce crește sarcina de calcul și întărește justificarea optimizării.

### Impactul GDPR: cazul devine mai greu, nu mai ușor

Trebuie semnalat explicit, pentru că este contraintuitiv. Controlul accesului
cu persoane înrolate care consimt este un caz juridic relativ curat.
Supravegherea continuă a unui spațiu, cu păstrarea fotografiilor unor persoane
**care nu au consimțit**, intră în regimul video-supravegherii și cere:

- delimitarea strictă a zonei monitorizate (intrare privată, **nu** spațiu
  public sau stradă);
- semnalizarea prezenței supravegherii;
- justificarea interesului legitim și retenție limitată documentată.

Consecință practică de proiectare: zona acoperită de cameră trebuie definită și
documentată în lucrare, iar retenția automată a fotografiilor (7-30 zile) nu mai
este o opțiune recomandată, ci o cerință.

### Hardware eliminat

Nu se mai cumpără: yală electromagnetică, alimentator de 12 V, modul releu
pentru încuietoare. Dispare și riscul electric asociat. Modulul RTC devine
**mai** important, nu mai puțin: jurnalul cu fotografii este acum singurul
produs al sistemului, iar un timestamp nefiabil îl invalidează complet.

### Puncte închise după D3 (confirmate de utilizatoare, 1 noiembrie 2026)

1. **Actuator hardware local: buzzer pe GPIO.** Se păstrează un actuator
   fizic, comandat prin GPIO în urma unei decizii AI locale, fără componentă
   periculoasă. Capitolul de hardware al lucrării rămâne cu senzor (cameră) și
   element de ieșire (buzzer).
2. **Rolul `PHYSICAL_ONLY` s-a redenumit `MONITORED`**, prin migrarea 4.
   Numele vechi este respins de constrângerea `CHECK` a schemei, iar rândurile
   existente au fost mapate automat la migrare.
3. **Multi-cameră pe un singur hub.** Un Pi 4 are un port CSI și patru USB,
   deci mai multe camere înseamnă mai multe fluxuri pe același hub, nu mai
   multe Raspberry Pi. Camera oficială CSI este alegerea pentru inferență
   continuă: trece prin ISP-ul hardware, deci dă pixeli gata de folosit, în
   timp ce o cameră USB cu MJPEG cere decodare JPEG pe CPU la fiecare cadru.

### Principiul care le face compatibile cu obiectivul științific

Sistemul se împarte în două planuri cu cerințe opuse:

- **Planul de decizie** (cameră → embedding → comparație → buzzer GPIO):
  integral local, offline, determinist. Nu depinde de rețea în nicio
  formă — nici verificare, nici timeout. Nu se modifică.
- **Planul de administrare** (jurnal, înrolare, permisiuni): accesibil de la
  distanță prin canal criptat. Indisponibilitatea lui nu afectează
  clasificarea detecțiilor și nici alerta locală.

Formularea pentru lucrare: decizia de acces este luată integral local, fără
dependență de rețea; administrarea este accesibilă remote printr-un canal
criptat, iar căderea acestui canal nu afectează funcționarea încuietorii.

Regulă de fier: **decizia de deschidere nu trece niciodată prin internet.**

### D1 — Acces remote prin VPN, nu prin expunerea API-ului

Decizia: VPN către rețeaua de acasă. **Tailscale** ca implementare primară
(fără port forwarding, funcționează și în spatele CGNAT, nume de host stabil
identic din casă și din afară), **WireGuard** ca alternativă fără dependențe
externe, dacă se obține IP public.

Respinse explicit:

- **Port forwarding** — API-ul care comandă o încuietoare fizică ar deveni
  public și ar fi găsit de scanere automate în câteva ore. Nu este apărabil.
- **Cloudflare Tunnel ca soluție permanentă** — traficul este decriptat la
  un terț, inacceptabil pentru date biometrice. Poate fi folosit *doar*
  punctual, pentru o demonstrație dintr-un browser străin.

Consecința tehnică importantă: prin VPN, telefonul primește o adresă virtuală
în rețeaua privată a proiectului și poate ajunge la adresa locală a Pi-ului.
Prin urmare **nu este necesară nicio modificare în codul API pentru a trece de
la LAN la acces remote**; se schimbă doar URL-ul configurabil al backendului,
dacă implementarea VPN nu oferă rutare transparentă. Cu Tailscale se poate
folosi numele stabil al dispozitivului Pi. Nu se expune portul FastAPI în
internet și nu se face port forwarding pentru API.

Fluxul operațional este:

1. Se instalează clientul VPN pe Raspberry Pi și pe telefon.
2. Pi-ul și telefonul sunt autorizate în aceeași rețea privată VPN.
3. Backendul FastAPI rămâne legat de interfața locală/VPN, nu de un port public.
4. Aplicația mobilă apelează API-ul prin adresa VPN sau numele privat al Pi-ului.
5. Raspberry Pi autentifică utilizatoarea prin JWT și aplică în continuare RBAC.
6. Când VPN-ul cade, administrarea și notificările live se opresc, dar decizia
   locală a ușii și jurnalizarea pe Pi continuă independent.

VPN-ul criptează canalul dintre telefon și Pi; nu transformă telefonul într-un
dispozitiv de procesare biometrică și nu mută baza de date în cloud. Tailscale
poate folosi un serviciu de coordonare pentru conectarea dispozitivelor, dar
traficul aplicației este criptat între capete și datele biometrice nu sunt
trimise serviciului de coordonare. Dacă cerința devine „fără niciun serviciu
extern, inclusiv pentru coordonarea VPN”, alternativa este WireGuard administrat
direct, cu endpoint public sau rutare proprie; aceasta necesită configurare
suplimentară de rețea și nu trebuie confundată cu expunerea API-ului.

Obligații pe care accesul remote le impune (nu funcționalități noi):

1. **Autentificarea devine condiție de existență.** Nu se instalează acces
   remote înainte ca login-ul să existe. Era deja pasul 1 din plan.
2. Token JWT cu durată scurtă (circa 15 minute) plus refresh token.
3. `CORSMiddleware` trebuie restrâns la lista exactă de origini.
4. Limitare la autentificare: maxim circa 5 încercări pe minut per IP.
5. TLS este obligatoriu **doar** în variantele fără VPN. WireGuard criptează
   deja tot traficul, deci HTTP simplu în interiorul tunelului este
   acceptabil.

Pentru demonstrația în fața comisiei nu se depinde de internetul sălii:
Pi-ul se conectează la un router mic sau la hotspot-ul telefonului, iar
accesul se face direct în rețeaua locală. Prin urmare **calea LAN trebuie să
rămână funcțională** chiar dacă VPN-ul este folosit zilnic, iar URL-ul de
bază al API-ului trebuie configurabil în aplicație, nu scris fix în cod.

### D2 — Fotografie salvată DOAR pentru persoană neidentificată

Decizia: nivelul „jurnal de audit cu imagini", nu flux video de la distanță.
La un eveniment `INTRUDER` sau `EMPTY_WHITELIST` — singurele în care persoana
nu a fost identificată — se salvează un JPEG mic și se atașează evenimentului.
Aplicația afișează evenimentul cu imaginea atașată.

Ce **nu** se salvează, intenționat:

- nicio imagine pentru evenimente `KNOWN` sau `UNEXPECTED_ZONE` — identitatea
  este deja în jurnal, imaginea nu adaugă informație;
- nicio imagine la înrolare — fluxul rămâne cel existent: backendul extrage
  fața 112×112×3, calculează embedding-ul, **aruncă fotografia**, salvează
  doar vectorul.

Justificarea pentru lucrare, pe principii GDPR: minimizarea datelor
(se păstrează doar ce este necesar), limitarea scopului (exclusiv probă de
securitate pentru tentative neautorizate), retenție limitată (ștergere
automată). Faptul că restricția este deliberată și documentată este un plus
la apărare, nu o limitare.

Design concret, de implementat în Faza 3:

- Coloană nouă în `logs`: `snapshot_path TEXT` (poate lipsi). Se adaugă
  printr-o migrare, împreună cu entitatea `cameras`:

  ```python
  (
      N,
      "Adaugă snapshot_path pentru evenimentele fără persoană identificată",
      ("ALTER TABLE logs ADD COLUMN snapshot_path TEXT",),
  )
  ```

- Locația fișierelor: `backend/data/snapshots/<AAAA-LL-ZZ>/<log_id>.jpg`,
  grupate pe zile ca ștergerea prin retenție să fie o simplă ștergere de
  director. Exclus din Git.
- Servire: rută dedicată, de exemplu `GET /api/logs/{id}/snapshot`, accesibilă
  **doar** cu autentificare și **doar** rolului `ADMIN`. Imaginile nu se
  includ niciodată în răspunsul de listare a logurilor.
- Retenție: implicit 30 de zile, configurabilă. Necesită o sarcină periodică
  de curățare; fără ea arhiva crește nelimitat.
- Ordinea de scriere: fișierul se scrie întâi, logul se inserează după, cu
  calea. Un log care referă un fișier inexistent trebuie tratat ca imagine
  absentă, nu ca eroare — ștergerea prin retenție produce exact această
  situație, în mod normal.
- Dimensionare: circa 30 KB per eveniment la 640×480. La 50 de evenimente
  refuzate pe zi rezultă aproximativ 45 MB pe lună, nesemnificativ pe un card
  de 32 GB — dar limita de retenție rămâne obligatorie.

### Fluxul video live — doar în rețeaua locală

Fluxul video rămâne disponibil exclusiv în LAN, nu prin VPN de la distanță.
Două motive: upload-ul unei conexiuni casnice este mult mai mic decât
download-ul și ar fi saturat de un flux continuu; și, mai important, un flux
video consumă CPU, RAM pentru buffere și bandă — **exact resursele măsurate
în Fazele 3 și 4**.

Regulă metodologică obligatorie: baseline-ul se măsoară **fără** streaming și
fără scrierea de fotografii. Scenariul cu streaming se măsoară separat și se
raportează separat. Amestecate, cifrele nu mai pot atribui diferențele
optimizărilor NEON, iar contribuția științifică a Fazei 4 devine
nedemonstrabilă.

Observație de hardware relevantă: o cameră USB care produce direct MJPEG
permite retransmiterea cadrelor deja comprimate, aproape fără cost CPU.
Camera CSI sau H.264 implică o compresie care costă. Alegerea camerei
influențează direct fezabilitatea streamingului.

### Cerință hardware descoperită: ceas de timp real

Raspberry Pi nu are ceas cu baterie. După o pană de curent, fără rețea,
ceasul pornește de la o valoare arbitrară. `backend/app/repositories/log_repo.py`
generează `timestamp` din ceasul sistemului, deci logurile de acces ar primi
date complet greșite — inacceptabil pentru un jurnal de audit care acum
include și fotografii.

Soluția aleasă pentru un sistem offline: **modul RTC pe magistrala I2C**
(circa 10–15 lei). NTP ar rezolva problema, dar reintroduce dependența de
internet exact pe planul care trebuie să rămână autonom. A treia variantă —
marcarea logurilor ca nesigure până la prima sincronizare — este corectă, dar
greu de apărat.

## Structura proiectului observată

```text
Licenta/
├── backend/
│   ├── main.py
│   ├── requirements.txt          # versiuni FIXATE
│   ├── app/
│   │   ├── config/
│   │   │   ├── database.py       # conexiuni + mecanismul de migrare
│   │   │   └── security.py       # bcrypt, JWT, limitare de rată
│   │   ├── dependencies/
│   │   │   └── auth.py           # dependențele care aplică autentificarea și RBAC
│   │   ├── repositories/
│   │   │   ├── camera_repo.py
│   │   │   ├── user_repo.py
│   │   │   └── log_repo.py
│   │   ├── routers/
│   │   │   ├── auth_router.py
│   │   │   ├── user_router.py
│   │   │   ├── camera_router.py
│   │   │   ├── log_router.py
│   │   │   ├── detection_router.py
│   │   │   └── simulation_router.py
│   │   ├── schemas/
│   │   │   ├── auth_schema.py
│   │   │   ├── user_schema.py
│   │   │   ├── camera_schema.py
│   │   │   ├── detection_schema.py
│   │   │   └── log_schema.py
│   │   └── services/
│   │       ├── auth_service.py
│   │       ├── user_service.py
│   │       ├── camera_service.py
│   │       ├── detection_service.py  # clasificarea fail-loud
│   │       ├── matching.py           # BASELINE: a nu se optimiza
│   │       ├── whitelist_cache.py
│   │       └── log_service.py
│   ├── tests/
│   │   ├── __init__.py
│   │   ├── base.py               # bază temporară + client autentificat
│   │   ├── test_api.py           # CRUD + simulare + paginare + coerență
│   │   ├── test_auth.py          # autentificare + aplicarea RBAC
│   │   ├── test_cameras.py       # camere + validarea permisiunilor
│   │   ├── test_detection.py     # clasificare, prag, politica de fotografii
│   │   └── test_migrations.py    # mecanismul de migrare
│   ├── tools/
│   │   ├── create_admin.py       # creează primul ADMIN (bootstrap local)
│   │   └── inspect_db.py         # utilitar de depanare, nu parte din aplicație
│   └── data/                     # baza SQLite + jwt_secret.key, excluse din Git
├── frontend/
│   ├── App.tsx
│   ├── app.json
│   ├── index.ts
│   ├── package.json
│   └── package-lock.json
├── .venv/                        # mediu virtual Python 3.12
├── .gitignore
└── README.md
```

Fișierele versiunii Firestore (`backend/database.py`, `backend/app/config/firebase.py`,
`backend/firebase_credentials.json`) au fost șterse. Nu există nicio referință
rămasă la Firebase în backend.

## Backend — implementat pentru dezvoltare locală fără hardware

Backendul folosește FastAPI. `backend/main.py` creează aplicația, configurează CORS și înregistrează routerele pentru whitelist și loguri. Ruta rădăcină `GET /` returnează un mesaj de confirmare. Documentația generată automat de FastAPI este disponibilă la `/docs`, iar schema OpenAPI la `/openapi.json`.

Codul este împărțit pe straturi:

- **Routers** (`backend/app/routers/`) declară rutele HTTP și validează cererile cu schemele Pydantic.
- **Services** (`backend/app/services/`) aplică logica aplicației și transformă situațiile de tip „nu există” sau „cerere goală” în răspunsuri HTTP.
- **Repositories** (`backend/app/repositories/`) citesc și scriu datele în SQLite.
- **Schemas** (`backend/app/schemas/`) descriu și validează datele de intrare/ieșire.
- **Config** (`backend/app/config/`) inițializează schema SQLite prin migrări (`database.py`) și oferă primitivele de securitate (`security.py`).
- **Dependencies** (`backend/app/dependencies/auth.py`) aplică autentificarea și rolurile, declarativ, pe fiecare rută.

### API autentificare

Prefixul rutelor este `/api/auth/`:

| Metodă | Rută | Rol necesar | Comportament |
|---|---|---|---|
| POST | `/api/auth/login` | — | Email + parolă; returnează token JWT, `expires_in`, `role`, `hub_id`, `user_id`. 401 la credențiale greșite, 429 la peste 5 încercări/minut. |
| GET | `/api/auth/me` | autentificat | Identitatea contului: rol, hub, nume, camere permise. Fără `embedding` și fără `password_hash`. |
| GET | `/api/auth/policy` | — | Parametri publici pentru ecranul de login (durata ferestrei de limitare). |

Token-ul se trimite în antetul `Authorization: Bearer <token>`.

### API whitelist / utilizatori

Prefixul rutelor este `/api/whitelist/`. **Toate rutele cer rolul ADMIN**, iar
`hub_id` este preluat din token, nu din cerere:

| Metodă | Rută | Comportament |
|---|---|---|
| GET | `/api/whitelist/` | Listează utilizatorii hub-ului apelantului. Răspunsul este `UserPublic[]`, fără `embedding`. |
| GET | `/api/whitelist/{doc_id}` | Returnează utilizatorul și logurile asociate; 404 dacă lipsește sau aparține altui hub. |
| POST | `/api/whitelist/` | Creează un utilizator; **201 Created**. 422 la combinație invalidă rol/email/parolă, 409 la email duplicat. |
| PUT | `/api/whitelist/{doc_id}` | Actualizare parțială cu `exclude_unset`, deci un câmp poate fi golit intenționat. 409 la retrogradarea ultimului ADMIN. |
| DELETE | `/api/whitelist/{doc_id}` | Șterge utilizatorul; 409 dacă este ultimul ADMIN al hub-ului. |

Schema de intrare acceptă `name`, `role`, `email`, `allowed_cameras`,
`embedding` și `password`. `hub_id` și `has_app_access` **nu** sunt acceptate
de la client: primul vine din token, al doilea este derivat din rol, ca să nu
existe două surse de adevăr. Rolurile permise sunt `ADMIN`, `APP_USER` și
`MONITORED`.

Parola este obligatorie pentru `ADMIN`/`APP_USER` (împreună cu emailul, care
este identitatea de login) și interzisă pentru `MONITORED`.

### API jurnal de supraveghere

Prefixul rutelor este `/api/logs/`:

| Metodă | Rută | Rol necesar | Comportament |
|---|---|---|---|
| GET | `/api/logs/?camera_id=cam_entrance&limit=100&offset=0` | ADMIN sau APP_USER | Pagină de evenimente: `{items, total, limit, offset}`. ADMIN vede tot hub-ul; APP_USER vede **doar propriile** evenimente, restricție impusă de server. |
| POST | `/api/logs/` | ADMIN | Creează un eveniment, cu timestamp UTC generat de backend; **201 Created**. Respinge cu 422 o combinație incoerentă status/identitate, iar `user_name` este derivat din persoana referită, nu preluat de la client. |
| DELETE | `/api/logs/` | ADMIN | Ștergere în masă, cu filtre opționale `camera_id`, `status`, `before`. Cere `confirm=true`; garda stă în stratul service, ca nicio altă cale de apel să nu o poată ocoli. Cu `before`, este mecanismul politicii de retenție din D2. |
| DELETE | `/api/logs/{doc_id}` | ADMIN | Șterge evenimentul; 404 dacă lipsește sau aparține altui hub. |

`limit` are valoarea implicită 100 și maximul 500. Ordonarea este
`timestamp DESC, id DESC` — al doilea criteriu previne repetarea sau sărirea
unui rând între pagini când două evenimente au același timestamp.

`snapshot_path` **nu** este expus în răspuns. Lista de loguri poate fi citită
și de un `APP_USER`, iar fotografiile intrușilor sunt date biometrice:
clientul primește doar `has_snapshot: true/false`. Servirea imaginii se face pe
o rută dedicată, restrânsă la ADMIN, care se implementează împreună cu captura
reală în Faza 3.

### API camere

Prefixul rutelor este `/api/cameras/`. Citirea este permisă oricui se poate
autentifica (aplicația are nevoie de numele camerelor ca să afișeze logurile
citibil); scrierea cere ADMIN, pentru că o cameră nouă extinde perimetrul
fizic controlat.

| Metodă | Rută | Rol | Comportament |
|---|---|---|---|
| GET | `/api/cameras/` | ADMIN sau APP_USER | Listează camerele hub-ului. |
| GET | `/api/cameras/{camera_id}` | ADMIN sau APP_USER | Detaliul unei camere; 404 dacă lipsește. |
| POST | `/api/cameras/` | ADMIN | Înregistrează o cameră; **201**. 409 dacă `camera_id` există deja în hub. |
| PUT | `/api/cameras/{camera_id}` | ADMIN | Modifică `name`, `kind`, `source`, `enabled`. |
| DELETE | `/api/cameras/{camera_id}` | ADMIN | Șterge camera; **409** dacă este încă permisă unor utilizatori. |

Cheia primară este compusă `(hub_id, camera_id)`: `camera_id` trebuie să fie
unic **în hub**, nu global, deci două hub-uri pot avea fiecare o cameră
numită `cam_entrance`.

`camera_id` este restrâns la `^[a-z0-9_]{2,40}$`. Motivul nu este estetic:
identificatorul ajunge în `allowed_cameras`, în URL-uri și în jurnalul de
audit, iar un identificator cu spații sau diacritice ar putea fi scris în mai
multe feluri, făcând comparația de permisiuni să eșueze silențios.

`camera_id` **nu poate fi redenumit** prin `PUT`: ar invalida tacit toate
referințele din `allowed_cameras` și din logurile deja scrise. Se schimbă doar
`name`, care este eticheta afișată.

Ștergerea unei camere încă acordate este **refuzată**, nu cascadată.
Alternativa — eliminarea automată din `allowed_cameras` — ar retrage permisiuni
fizice fără ca administratorul să fi cerut asta; într-un sistem de control al
accesului, o retragere tacită de drepturi este mai periculoasă decât o eroare
clară.

### API detecție

| Metodă | Rută | Rol | Comportament |
|---|---|---|---|
| POST | `/api/detection/evaluate` | ADMIN | Primește `camera_id`, `embedding` și opțional `snapshot_path`; returnează `outcome`, `reason`, scorul, pragul și id-ul evenimentului scris. |

Răspunsul este **mereu 200**, inclusiv la alertă: alerta este un rezultat
valid al operației, nu o eroare a cererii. Un 403 ar amesteca „tu, apelantul,
nu ai dreptul" cu „persoana din fața camerei nu este așteptată aici".

`score` și `threshold` sunt returnate intenționat. Fără ele o alertă nu poate
fi diagnosticată — „nu a fost recunoscut" și „a fost recunoscut la 0.48, sub
pragul de 0.5" arată identic — iar calibrarea pragului din Faza 3 ar fi orbă.

### SQLite local și simulare fără hardware

Repository-urile active folosesc SQLite, nu Firestore. Schema este inițializată prin migrări la pornirea FastAPI (vezi secțiunea despre `PRAGMA user_version`); baza implicită este `backend/data/access_control.sqlite3`, iar locația poate fi schimbată prin variabila `ACCESS_CONTROL_DB_PATH`. Directorul implicit este exclus din Git. Tabelele `users` și `logs` au indecși pentru hub/cameră/timestamp și utilizator; ștergerea unui utilizator păstrează logurile și setează `user_id` la `NULL`.

`POST /api/simulation/detection` creează un eveniment simulat — persoană cunoscută sau intrus — fără cameră și fără model AI, și cere rolul **ADMIN**. Pentru o persoană cunoscută este necesar un `user_id` existent, din același hub. Endpointul este destinat dezvoltării și nu constituie recunoaștere reală. Atenție: primește `expected` ca boolean de la client și îl crede, nu verifică `allowed_cameras` și nu compară niciun embedding, deci nu este un model pentru endpointul real de detecție. Restricția la ADMIN există pentru că altfel orice client ar putea falsifica jurnalul de audit.

Fișierele versiunii Firestore au fost șterse din proiect. Cheia de serviciu Google care exista în `backend/firebase_credentials.json` trebuie revocată din consola Google Cloud, pentru că a existat pe disc și în istoricul local de checkpoint-uri. Nu copia secrete în cod, documentație, mesaje de eroare sau repository.

SQLite permite dezvoltarea locală pe calculator și poate rula ulterior pe Pi, dar datele nu se sincronizează automat cu Firestore sau cu telefonul. Baza locală singură nu oferă acces remote, push notifications ori o aplicație frontend funcțională.

### Migrarea schemei (`PRAGMA user_version`)

Schema nu se mai creează ad-hoc la pornire. `backend/app/config/database.py`
conține un mecanism de migrare versionat, necesar pentru că schema este
definită în cod și trebuie aplicată și pe baze care există deja.

Problema rezolvată: `CREATE TABLE IF NOT EXISTS` este ignorat complet când
tabela există, deci o coloană adăugată acolo nu apare niciodată pe o bază
veche. Codul ar cere coloana, baza nu ar avea-o, iar eroarea `no such column`
ar apărea direct pe Raspberry Pi.

Mecanismul:

- `MIGRATIONS` este o secvență de `(versiune, descriere, instrucțiuni SQL)`.
- `LATEST_SCHEMA_VERSION` se calculează automat din `MIGRATIONS`.
- Versiunea fiecărei baze este stocată în fișier, în `PRAGMA user_version`.
- `initialize_database()` aplică doar migrările cu versiune mai mare decât
  cea din fișier, în ordine crescătoare, și returnează lista celor aplicate.
- Fiecare migrare rulează într-o tranzacție explicită `BEGIN`/`COMMIT`
  împreună cu incrementarea versiunii: ori se aplică integral, ori deloc.
- O bază cu versiune mai NOUĂ decât codul oprește pornirea cu `RuntimeError`,
  în loc să scrie într-o schemă necunoscută.

Migrarea 1 este o migrare de bază (*baseline*): folosește `IF NOT EXISTS`, ca
să funcționeze atât pe o bază goală, cât și pe baza existentă creată înainte
de introducerea mecanismului (`user_version = 0`, dar tabele prezente). Baza
reală din `backend/data` a fost adoptată astfel, fără pierdere de date, și
este acum la versiunea 1.

Regulă de lucru: o migrare deja livrată nu se modifică niciodată, pentru că
bazele existente au aplicat-o deja și nu o vor mai rula. Orice corecție devine
o migrare nouă, cu versiune următoare.

Migrările livrate până acum:

| Versiune | Conținut |
|---|---|
| 1 | schema de bază: `users`, `logs` și indecșii aferenți |
| 2 | `users.password_hash` + index unic parțial pe `email` |
| 3 | tabela `cameras`, `logs.snapshot_path` (decizia D2) și crearea camerei implicite pentru hub-urile care aveau deja utilizatori |
| 4 | vocabularul D3: rolul `MONITORED`, motivele de detecție, `cam_entrance`, `Unknown Person` |

Migrarea 3 conține și o migrare de **date**, nu doar de schemă: utilizatorii
existenți aveau `allowed_cameras = ["cam_intrare"]` (denumirea de atunci,
tradusă în `cam_entrance` de migrarea 4), iar din momentul în care
permisiunile sunt validate împotriva tabelei `cameras`, o tabelă goală ar fi
invalidat dintr-o dată toate permisiunile existente.

Migrarea 4 este tot o migrare de date: traduce rolurile, motivele, id-urile de
cameră și numele implicit, inclusiv în lista JSON din `allowed_cameras`.
Literalele românești din migrările 1-3 **nu se modifică niciodată** — o
migrare deja aplicată descrie schema de la momentul ei, iar editarea ei ar
face ca o bază nouă să primească altă schemă decât una existentă, ambele
raportând aceeași versiune.

Forma unei migrări noi:

```python
(
    4,
    "Descrierea schimbării",
    ("ALTER TABLE users ADD COLUMN embedding_dim INTEGER",),
)
```

Mecanismul este acoperit de `backend/tests/test_migrations.py`: bază goală,
idempotență la a doua pornire, adoptarea unei baze fără versiune cu păstrarea
datelor, și respingerea unei baze mai noi decât codul.

### Autentificare, RBAC și izolare multi-tenant

Implementat în versiunea API 0.3.0. Până aici, rolurile erau doar valori text
într-o coloană: nicio rută nu verifica identitatea apelantului. Firebase
Authentication oferea această funcționalitate ca serviciu; după trecerea la
SQLite, ea a devenit responsabilitatea aplicației.

**Fișiere noi**

| Fișier | Rol |
|---|---|
| `backend/app/config/security.py` | primitive criptografice: hash bcrypt, emitere/validare JWT, limitare de rată |
| `backend/app/schemas/auth_schema.py` | `LoginRequest`, `TokenResponse`, `CurrentUser` |
| `backend/app/services/auth_service.py` | verificarea credențialelor și emiterea token-ului |
| `backend/app/dependencies/auth.py` | dependențele FastAPI care aplică autentificarea și rolurile |
| `backend/app/routers/auth_router.py` | `POST /api/auth/login`, `GET /api/auth/me`, `GET /api/auth/policy` |
| `backend/tools/create_admin.py` | creează primul ADMIN, local, rezolvând dependența circulară de pornire |
| `backend/tests/base.py` | bază de test cu bază temporară, ADMIN existent și client autentificat |
| `backend/tests/test_auth.py` | teste pentru autentificare și aplicarea RBAC |

**Alegeri tehnice și motivele lor**

- **bcrypt**, nu o funcție hash rapidă (`sha256`). Viteza ajută atacatorul;
  bcrypt este lent deliberat și include un salt unic per parolă, deci două
  persoane cu aceeași parolă au hash-uri diferite.
- **PyJWT**, nu `python-jose`: mai puține dependențe, bibliotecă de referință.
- **HS256**, secret simetric: aceeași aplicație emite și verifică token-ul.
- Algoritmul este specificat explicit la decodare (`algorithms=["HS256"]`),
  ceea ce previne atacul în care un token este trimis cu `alg: none`.
- Costul bcrypt este configurabil prin `ACCESS_CONTROL_BCRYPT_ROUNDS` **doar**
  pentru teste (suita trecea de la 44 s la 9 s); producția folosește 12 runde.

**Regulile RBAC aplicate**

| Operație | ADMIN | APP_USER | MONITORED |
|---|---|---|---|
| Autentificare | da | da | **imposibilă prin construcție** |
| Listare/creare/modificare/ștergere persoane | da | 403 | — |
| Citire jurnal | tot hub-ul | **doar ale sale** | — |
| Scriere/ștergere evenimente, simulare | da | 403 | — |
| Profil propriu (`/api/auth/me`) | da | da | — |

`MONITORED` nu primește niciodată parolă: coloana `password_hash` rămâne
`NULL`, iar autentificarea eșuează fără cod special de verificare. Al treilea
nivel RBAC rezultă din schemă, nu din logică.

**Izolarea multi-tenant devine reală.** `hub_id` nu mai este parametru de
query sau câmp în corpul cererii: este preluat din token. Înainte, orice
client putea citi datele altui hub schimbând un parametru în URL, deci
izolarea era o convenție. Verificarea se aplică și la citirea unui utilizator
după `id` (404, nu 403 — un 403 ar confirma că id-ul există în alt hub).

**Decizii de securitate implementate**

- Mesaj unic la eșec de login (email inexistent, parolă greșită, cont fără
  acces produc același 401 cu același text), ca să nu se poată enumera
  conturile existente.
- Timp egalizat: când emailul nu există se consumă totuși timpul unei
  verificări bcrypt, altfel diferența de durată ar permite enumerarea.
- Limitare de rată la login: 5 încercări pe minut per IP, verificată înaintea
  oricărui calcul. Starea este în memoria procesului — suficient pentru un
  singur proces uvicorn pe Pi, nedistribuită între workeri.
- Token cu durată scurtă: 15 minute, conform deciziei D1 (acces remote).
- **Revocare imediată**: fiecare cerere reîncarcă utilizatorul din baza de
  date. Costă o citire SQLite în plus, dar un token valabil 15 minute ar
  funcționa altfel și după ștergerea contului. Pentru control de acces,
  revocarea nu poate aștepta expirarea.
- Schimbarea rolului invalidează token-ul (401, reautentificare necesară), în
  loc să ridice sau să păstreze privilegii vechi.
- Retrogradarea la `MONITORED` șterge `password_hash`, ca un fost
  `APP_USER` să nu păstreze credențiale valabile.
- Ultimul ADMIN al unui hub nu poate fi șters sau retrogradat (409): altfel
  recuperarea ar cere acces fizic la fișierul bazei.
- Secretul JWT vine din `ACCESS_CONTROL_JWT_SECRET`. În lipsa lui, în
  dezvoltare, se generează o dată și se păstrează în `backend/data/jwt_secret.key`
  (director exclus din Git). **Un secret implicit scris în cod a fost respins
  intenționat**: ar permite oricui citește repository-ul să emită token-uri.

**Scurgerile de date închise**

`GET /api/whitelist/` returna vectorul biometric (`embedding`) al fiecărui
utilizator către orice client. Modelele de ieșire `UserPublic` / `UserDetail`
elimină atât `embedding`, cât și `password_hash`. În locul vectorului există
`has_embedding: bool` — interfața are nevoie să știe *dacă* o persoană este
înrolată, nu care este vectorul ei.

**Bootstrap: primul administrator**

Toate rutele de administrare cer ADMIN, dar o bază nouă nu are niciun ADMIN.
Dependența circulară este rezolvată de `backend/tools/create_admin.py`, rulat
pe mașina respectivă. Rădăcina de încredere este accesul fizic la dispozitiv:
cine poate rula scriptul poate oricum modifica direct fișierul SQLite.

Alternativele au fost respinse explicit: o rută HTTP de inițializare activă
până la primul ADMIN ar fi o fereastră în care oricine din rețea preia
sistemul; o parolă implicită de administrator este cel mai răspândit mod în
care se compromit dispozitivele IoT.

```powershell
cd C:\Users\bianc\Desktop\Licenta\backend
python tools\create_admin.py --name "Bianca" --email bianca@exemplu.ro
```

Parola este cerută interactiv, nu ca argument — un argument ar rămâne în
istoricul terminalului.

**Paginare și CORS**

`GET /api/logs/` returnează acum `{items, total, limit, offset}`, cu `limit`
implicit 100 și maxim 500. Ordonarea include `id` ca al doilea criteriu,
altfel două evenimente din aceeași milisecundă ar putea fi repetate sau sărite
între pagini.

`allow_origins=["*"]` a fost înlocuit cu o listă explicită, configurabilă prin
`ACCESS_CONTROL_CORS_ORIGINS`.

### Clasificarea detecției: potrivire, prag, cache și fail-loud

Implementat în versiunea API 0.4.0, rescris de decizia D3 în 0.5.0.

**Fișiere noi**

| Fișier | Rol |
|---|---|
| `backend/app/repositories/camera_repo.py` | acces la date pentru `cameras` |
| `backend/app/services/camera_service.py` | reguli pentru camere + validarea `allowed_cameras` |
| `backend/app/schemas/camera_schema.py` | DTO-urile de cameră, cu formatul `camera_id` |
| `backend/app/routers/camera_router.py` | rutele `/api/cameras/` |
| `backend/app/services/matching.py` | **baseline-ul** de similaritate cosinus, Python pur |
| `backend/app/services/whitelist_cache.py` | cache-ul în memorie al fețelor înrolate |
| `backend/app/services/detection_service.py` | clasificarea detecției, fail-loud |
| `backend/app/schemas/detection_schema.py` | cererea, rezultatul și invariantul de coerență |
| `backend/app/routers/detection_router.py` | ruta `/api/detection/evaluate` |
| `backend/tests/test_cameras.py`, `test_detection.py` | testele de camere și de clasificare |

**Serviciul este transport-agnostic, intenționat.** `DetectionService.evaluate()`
nu ridică `HTTPException` și nu știe nimic despre HTTP, pentru că apelantul
principal va fi bucla de recunoaștere de pe Raspberry Pi, care rulează **în
același proces** și nu are cerere, răspuns sau cod de stare. Ruta HTTP este un
al doilea apelant al aceleiași funcții, pentru testare și demonstrație.

**Fail-loud, fără excepții.** `evaluate()` nu ridică niciodată o excepție.
Orice situație neprevăzută — cameră inexistentă sau dezactivată, whitelist
goală, vector de dimensiune incompatibilă, eroare internă — produce un
rezultat, niciodată tăcere. Până la D3 rezultatul implicit era `DENIED`,
pentru că sistemul comanda o yală și „nu știu" trebuia să aibă același efect
fizic ca „nu". După D3 rezultatul implicit este `FAULT` cu motivul `DEGRADED`:
într-un sistem de supraveghere, tăcerea este varianta periculoasă, iar o
excepție propagată în bucla de cadre ar opri supravegherea cu totul.

Garanția e verificată de un test care injectează un repository ce aruncă
mereu — echivalentul cel mai apropiat al unei baze căzute pe Pi.

Rezultatul are **două niveluri separate**, nu unul. `reason` este motivul fin,
scris în jurnal și numărat în capitolul de evaluare: `KNOWN`, `INTRUDER`,
`UNEXPECTED_ZONE`, `EMPTY_WHITELIST`, `CAMERA_UNKNOWN`, `CAMERA_DISABLED`,
`DEGRADED`. `outcome` este ce trebuie **făcut**: `KNOWN`, `ALERT` sau `FAULT`.
Maparea trăiește într-un singur loc, `OUTCOME_BY_REASON`.

Separarea există pentru că alerta de intrus și alerta de defect au
destinatari diferiți: prima e un semnal de securitate, a doua e mentenanță.
Contopite, o cameră stricată ar produce notificări care arată ca tentative de
intrare, iar utilizatorul ar învăța să le ignore — exact comportamentul care
face un sistem de alertare inutil.

Două clasificări care par surprinzătoare și sunt deliberate: `EMPTY_WHITELIST`
este `ALERT`, nu `FAULT`, pentru că o casă păzită fără nimeni înrolat trebuie
să alerteze la oricine apare; `CAMERA_DISABLED` este `FAULT`, nu `ALERT`,
pentru că administratorul a oprit camera intenționat, dar o buclă care
trimite cadre de pe ea înseamnă configurație incoerentă.

**Ordinea verificărilor este deliberată: camera întâi, identitatea după.** O
cameră dezactivată este clasificată înainte de orice comparație, deci nu se
consumă CPU degeaba — ceea ce contează pe Pi, unde bucla rulează continuu.

**O alertă pentru persoană cunoscută păstrează identitatea în jurnal.** Dacă
fața se potrivește dar camera nu este o zonă așteptată, evenimentul conține
`user_id` și numele. O alertă anonimă ar face imposibil de aflat cine a fost
unde — exact întrebarea pentru care există un jurnal de audit.

**Cache-ul whitelist-ei** (`whitelist_cache`) ține în memorie doar utilizatorii
cu embedding înrolat. Invalidarea este **explicită, nu pe timp**: `UserService`
apelează `invalidate(hub_id)` după orice creare, modificare sau ștergere. Un
cache cu TTL ar însemna o fereastră în care o persoană ștearsă încă nu
generează alertă — inacceptabil, chiar dacă durează câteva secunde.
Invalidarea se face după *orice* modificare, nu doar la schimbarea feței: o
modificare a `allowed_cameras` schimbă rezultatul la fel de direct.

Limitare cunoscută: cache-ul trăiește în memoria procesului. Cu mai mulți
workeri uvicorn fiecare ar avea propria copie, iar invalidarea unuia nu ar
ajunge la ceilalți. Arhitectura rulează un singur proces pe Pi, deci situația
nu apare; dacă se adaugă workeri, invalidarea trebuie să devină un semnal
între procese.

**`matching.py` este baseline-ul științific și NU trebuie optimizat.** Este
scris în Python pur, fără numpy, intenționat: dependențele de pe Pi rămân
minime, iar măsurătoarea reflectă Python pur, nu BLAS-ul optimizat din spatele
numpy — ceea ce ar amesteca două optimizări diferite în aceeași cifră. Exact
`cosine_similarity` și `find_best_match` sunt funcțiile înlocuite în Faza 4 de
nucleul C/C++ cu intrinseci ARM NEON. Cifrele de referință (latență per cadru,
FPS, RAM) trebuie colectate cu această versiune.

Candidații cu dimensiune incompatibilă sunt **ignorați**, nu tratați ca
eroare: o whitelist poate conține temporar vectori produși de o versiune
anterioară a modelului, iar o excepție ar bloca întreaga buclă pentru un
singur rând vechi. Ignorarea face ca persoana să nu fie recunoscută — deci
produce o **alertă de intrus**, nu tăcere. După D3 asta este comportamentul
corect: o notificare falsă se inspectează și se închide, un intrus ratat nu
se observă niciodată.

**Pragul (`ACCESS_CONTROL_MATCH_THRESHOLD`, implicit 0.5) nu este o valoare
validată de securitate.** Este un punct de pornire. Trebuie calibrat în Faza 3
pe date reale, raportând rata de respingere falsă și rata de acceptare falsă,
iar valoarea aleasă trebuie documentată în lucrare. Un prag necalibrat pe un
sistem de supraveghere este o vulnerabilitate, nu un detaliu de configurare.

**Aplicarea deciziei D2 este în cod, într-un singur loc.** `DetectionService._build`
păstrează `snapshot_path` doar când persoana **nu** a fost identificată. Dacă
persoana este cunoscută, imaginea este aruncată — identitatea ei este deja
în jurnal, iar o fotografie în plus ar fi date biometrice fără scop. La un
defect nu se păstrează nimic. Testele verifică toate cazurile.

**Limitare de securitate, de rezolvat înainte de un nod de cameră separat:**
ruta `/api/detection/evaluate` cere rolul ADMIN, adică o identitate de OM. Un
dispozitiv nu are email și parolă. Pentru un al doilea dispozitiv care întreabă
hub-ul este nevoie de autentificare de mașină — un token de dispozitiv, emis
per cameră și revocabil independent de conturile utilizatorilor. Nu a fost
inventat acum, ca să nu existe un al doilea mecanism de autentificare
nefolosit și netestat.

### Mediul local și pornirea backendului

Mediul virtual `.venv` din rădăcina proiectului este funcțional și conține
pachetele din `backend/requirements.txt`, cu **versiuni fixate**. Fixarea
este necesară pentru reproductibilitate: aceleași versiuni trebuie să
funcționeze pe laptop (Windows x86_64) și pe Raspberry Pi (ARM64).

Rutina de pornire:

```powershell
cd C:\Users\bianc\Desktop\Licenta
.\.venv\Scripts\Activate.ps1
cd backend
python -m uvicorn main:app --reload --port 8000
```

După activare promptul afișează `(.venv)`, iar comanda `python` folosește
interpretorul din mediul virtual. Activarea este valabilă doar în fereastra
curentă de terminal.

Capcane de mediu, verificate:

- Pe acest laptop există Python 3.12 **și** 3.14. Comanda `py` fără argument
  pornește 3.14, care nu are pachetele proiectului. Fără venv activat,
  versiunea corectă se invocă explicit: `py -3.12`.
- `main.py` se află în `backend`, iar importurile sunt de forma
  `from app.config...`. Pornirea din rădăcină fără `--app-dir backend` nu
  găsește modulul `main`.
- Dacă `Activate.ps1` este blocat de politica de execuție Windows, se
  rezolvă o singură dată cu
  `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`.

Testele automate, din folderul `backend`:

```powershell
python -m unittest discover -s tests -v
```

Starea curentă: 60 de teste, toate trec (migrări, CRUD, paginare,
autentificare, RBAC, camere, permisiuni per cameră, decizie de acces,
politica de fotografii).

Variabile de mediu recunoscute:

| Variabilă | Rol | Obligatorie |
|---|---|---|
| `ACCESS_CONTROL_DB_PATH` | locația fișierului SQLite | nu (implicit `backend/data/`) |
| `ACCESS_CONTROL_JWT_SECRET` | secretul de semnare a token-urilor, minim 32 de bytes | **da pe Raspberry Pi** |
| `ACCESS_CONTROL_CORS_ORIGINS` | originile permise, separate prin virgulă | nu (implicit localhost) |
| `ACCESS_CONTROL_MATCH_THRESHOLD` | pragul de similaritate cosinus | nu (implicit 0.5, **de calibrat**) |
| `ACCESS_CONTROL_BCRYPT_ROUNDS` | costul bcrypt; doar pentru teste | nu (implicit 12) |

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
| 1. Backend și DB | Funcțional și securizat | FastAPI pe 3 straturi, JWT + bcrypt, RBAC aplicat prin dependențe, izolare multi-tenant din token, entitate `cameras` cu permisiuni validate, clasificare fail-loud cu prag și cache de whitelist, jurnal paginat cu ștergere în masă și invariant de coerență, migrări versionate (schema 4), 78 de teste automate. **Rămâne de validat pe Raspberry Pi** (restart, offline, wheel-uri ARM64). |
| 2. Frontend Expo | Început | `expo-router` + React Native Paper + temă Material 3, client HTTP tipizat, stocare token (SecureStore pe telefon, localStorage pe web), ecrane: autentificare, jurnal, profil. Rulează pe iOS, Android și browser din același cod. Rămân: paginare și filtre în jurnal, ecranele de persoane și camere, înrolarea feței. |
| 3. AI și hardware | Neîncepută | Nu există încă pipeline OpenCV/Tiny-ResNet, GPIO sau baseline măsurat. Contractul de detecție și baseline-ul de potrivire (`matching.py`) există deja, deci bucla de cadre are unde să se conecteze. Include deciziile D1 (Tailscale/WireGuard) și D2 (fotografie doar pentru persoană neidentificată), calibrarea pragului, buzzer-ul pe GPIO, modulul RTC, și agregarea detecțiilor consecutive într-un singur eveniment. |
| 4. Optimizări C/C++ | Neîncepută | Nu există încă extensie Cython/C++, IM2COL pe blocuri, cache blocking, NEON sau layer fusion. |

## Lipsuri cunoscute în Faza 1

Rezolvate: autentificarea, aplicarea RBAC, `response_model` (scurgerea
`embedding`), paginarea jurnalului, CORS restrâns, semantica `UserUpdate`
(`exclude_unset`), entitatea `cameras` cu validarea permisiunilor,
endpointul de detecție fail-loud, ștergerea în masă a jurnalului cu gărzile
ei, și invariantul de coerență status/identitate. Rămân, în ordinea
dependențelor:

1. **`HTTPException` este ridicat în straturile service pentru utilizatori,
   camere și jurnal.** `DetectionService` este deja transport-agnostic (nu
   ridică excepții HTTP), dar celelalte servicii nu sunt. Traducerea în HTTP ar
   trebui făcută prin excepții de domeniu și `exception_handler` în `main.py`.
2. **Embedding-ul nu are `embedding_dim` și `model_version`.** La înlocuirea
   inferenței PyTorch cu nucleul NEON trebuie demonstrat că ambele produc
   vectori comparabili; fără coloană de versiune nu se pot distinge
   embedding-urile vechi de cele curente. `find_best_match` ignoră deja
   vectorii de dimensiune incompatibilă, dar nu poate deosebi două modele cu
   aceeași dimensiune. Formatul JSON text forțează și o parsare per rând la
   încărcarea cache-ului, ceea ce contează la 2 GB.
3. **Pragul de similaritate nu este calibrat.** Valoarea implicită 0.5 este un
   punct de pornire, nu o valoare de securitate. Calibrarea cu FAR/FRR
   raportate este o cerință a Fazei 3.
4. **Politica de retenție are mecanismul, nu are automatizarea.**
   `DELETE /api/logs/?before=...` face ștergerea cerută de D2, dar nimic nu o
   apelează periodic, iar ruta de servire a imaginii
   (`GET /api/logs/{id}/snapshot`, doar ADMIN) nu există. Ștergerea rândului
   nu șterge încă JPEG-ul de pe disc — răspunsul raportează câte rânduri
   șterse aveau fotografie exact ca să nu se producă fișiere orfane în
   necunoștință. Se implementează împreună cu captura reală, în Faza 3.
5. **Ruta `/api/detection/evaluate` nu are autentificare de mașină.** Cere
   rolul ADMIN, adică o identitate de om. Un nod de cameră separat are nevoie
   de un token de dispozitiv, revocabil independent.
6. **Două fișiere `.pyc` sunt încă urmărite de Git**
   (`backend/__pycache__/*.pyc`), intrate înainte de regula din
   `.gitignore`; necesită `git rm --cached`.
7. **Cheia de serviciu Google nu a fost revocată.** Fișierul a fost șters,
   dar cheia poate fi activă în continuare în Google Cloud. Doar
   utilizatoarea are acces în consolă.
8. **Nimic nu a fost validat pe Raspberry Pi**: persistență după restart,
   funcționare fără internet, disponibilitatea wheel-urilor pe ARM64.

## Plan: persistență locală și operare offline

### Decizia de arhitectură

Pentru cerința strictă „zero-cloud”, Raspberry Pi-ul trebuie să poată citi și scrie datele de acces fără Firebase sau internet. Decizia pentru acest proiect este SQLite local ca sursă principală de adevăr. SQLite face parte din biblioteca standard Python (`sqlite3`), nu cere un server separat și este potrivit pentru dimensiunea redusă a bazei de date a proiectului. Un prim backend local a fost implementat și poate fi dezvoltat pe calculator înainte să existe hardware.

Firebase/Firestore nu trebuie apelat în fluxul normal de verificare a accesului. O sincronizare opțională cu un serviciu la distanță ar fi o funcționalitate separată, ulterioară, și ar contrazice o interpretare strictă zero-cloud dacă devine necesară pentru funcționare.

### Etapa 1 — stabilește datele păstrate local

Definește schema SQLite pentru:

- **users**: ID stabil, `hub_id`, nume, rol, acces la aplicație, email, camere permise, embedding-ul facial și metadatele modelului (versiune și dimensiune).
- **logs**: ID, `hub_id`, cameră, persoană (poate lipsi, pentru o față neidentificată), nume, rezultat (`status`, din vocabularul `DetectionReason`) și timestamp UTC.

Păstrează embedding-urile într-un format binar compact sau într-un format serializat cu versiunea/dimensiunea explicită; alege reprezentarea după ce este stabilit formatul numeric folosit de model. Imaginile faciale brute nu se salvează, cu o singură excepție stabilită prin decizia D2: evenimentele `INTRUDER` și `EMPTY_WHITELIST`, adică exact cele în care persoana nu a fost identificată, cu retenție limitată și servire doar către `ADMIN` autentificat.

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

Scrie rezultatul fiecărei detecții în jurnalul SQLite, inclusiv pentru fețele neidentificate. Comandă buzzer-ul numai după o clasificare locală validă și păstrează comportamentul **fail-loud** când baza, camera sau modelul nu sunt disponibile: alertă de defect, niciodată tăcere (decizia D3).

### Etapa 6 — backup și operare

Documentează locația bazei, backup-ul, restaurarea și migrarea versiunilor de schemă. Folosește permisiuni de sistem de operare restrictive pentru fișierul SQLite și backup-uri. Verifică spațiul disponibil și comportamentul la oprire neașteptată. WAL poate fi evaluat pentru acces concurent, dar trebuie folosit împreună cu backup corect (nu copia doar fișierul principal cât timp baza este activă).

### Sincronizarea cu Firebase — opțională, nu parte din MVP offline

Dacă ulterior se cere replicarea în cloud, trateaz-o ca un strat separat: coadă/outbox locală cu ID-uri de operații stabile, retry cu backoff, idempotency și politică explicită de rezolvare a conflictelor. Accesul, decizia facială și logarea locală nu trebuie să aștepte sincronizarea. Dacă obiectivul rămâne strict zero-cloud, nu implementa acest strat.

## Următorii pași recomandați

Ordinea respectă dependențele reale, nu preferințele. Autentificarea + RBAC,
`response_model`, paginarea, entitatea `cameras` cu permisiuni validate și
endpointul de detecție fail-loud sunt **implementate** — vezi secțiunile
„Autentificare, RBAC și izolare multi-tenant" și „Clasificarea detecției".
Primul ADMIN este creat, iar camera implicită `cam_entrance` există.

1. **Jurnalul complet în Expo**: paginare, filtre pe cameră/rezultat/dată,
   ecran de detaliu eveniment. Folosește rute care există deja și este
   ecranul arătat la fiecare demonstrație.
2. **Restul ecranelor Expo**: persoane monitorizate (listă, detaliu, editare
   rol și zone), camere (CRUD complet), curățarea jurnalului, și gărzi de rol
   în interfață, ca un `APP_USER` să nu vadă butoane care răspund 403.
   Decizie încă deschisă: stratul de date (bibliotecă de cache sau cod scris
   de mână), necesar înainte de ecranele care **modifică** date.
3. **Spike de validare a modelului pe laptop**, înainte de a cumpăra hardware:
   detecție față, normalizare 112×112×3, embedding, și verificarea pe 20-30 de
   fotografii că similaritatea cosinus separă corect „aceeași persoană" de
   „persoane diferite". Este riscul cel mai mare din tot planul: dacă modelul
   nu produce vectori discriminativi, pragul nu se poate calibra și Faza 4 ar
   optimiza un model care nu funcționează.
4. **Înrolarea feței**, care depinde de spike: cere o rută nouă de upload de
   imagine în backend (astăzi `POST /api/whitelist/` primește vectorul direct),
   apoi ecranul.
5. **`embedding_dim` și `model_version`** pe persoană, înainte de Faza 3.
6. **Excepții de domeniu în loc de `HTTPException`** în serviciile pentru
   utilizatori, camere și jurnal, ca întregul strat service să fie apelabil din
   bucla Edge AI. `DetectionService` respectă deja această regulă.
7. **Validare pe Raspberry Pi**: persistență după restart, funcționare fără
   internet, `ACCESS_CONTROL_JWT_SECRET` setat ca variabilă de mediu a
   serviciului.
8. **Abia apoi** pipeline-ul AI de bază: captura OpenCV, normalizarea
   112×112×3, inferența Tiny-ResNet, conectarea la
   `DetectionService.evaluate()` și comanda buzzer-ului prin GPIO.
   Măsurătorile de referință (RAM, latență per cadru, FPS) se colectează
   ÎNAINTE de orice optimizare C/C++ și ÎNAINTE de activarea scrierii de
   fotografii. Fără aceste cifre, Faza 4 nu are cu ce să se compare.
9. **Agregarea detecțiilor**: cineva care stă 30 de secunde în cadru la 10 FPS
   produce 300 de detecții identice. Fără grupare pe identitate și cameră,
   jurnalul devine inutilizabil și notificările devin zgomot. Muncă nouă în
   stratul service, apărută odată cu D3.
10. **Calibrarea pragului** cu FAR/FRR raportate, ca parte din Faza 3.

Regulă de întreținere: acest document se actualizează după fiecare etapă.
Este singura apărare împotriva pierderii contextului între sesiuni de lucru
cu unelte diferite.
