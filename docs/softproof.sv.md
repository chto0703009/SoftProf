# SoftProf

Handbok - version 2.5.2 - 7 november 2026

Christer Törnkvist - christer@borgasundsfotografiska.se
GNU GPL version 3 eller senare (GPL-3.0-or-later).

## 1. Installera och kom igång

SoftProf jämför en bild med en beräknad simulering av dess utskrift. Du kan undersöka följderna av vald arbetsfärgrymd, skrivar-/pappersprofil, återgivningsmetod och svartpunktskompensation innan du sparar en konverterad bild.

### Installera appen

Öppna `SoftProf-2.5.2-macos.dmg`, välj **Apple Silicon** eller **Intel** efter datorns processor och dra den appen till **Applications / Program**, mata ut skivavbilden och starta appen från Program. DMG-filen har två märkta appar: **Apple Silicon kräver macOS 14+; Intel kräver macOS 13 Ventura+**. Apple Silicon är ARM64; Intel är x86_64. Alla Intel-binärer kontrolleras mot Venturas systemkrav. Fysisk Ventura-maskin har inte testats här. Installera bara rätt app för din dator. Python och nödvändiga bibliotek ingår; utvecklingsprojektet behövs inte.

Paketet är ad hoc-signerat men saknar Developer ID-signering och Apple-notarisering. Om macOS blockerar första starten, granska appen i **Systeminställningar > Integritet och säkerhet > Öppna ändå**. DMG-filen innehåller båda handböckerna, GPL-licensen och appens källkod.

### Välj rätt app för din dator

| Dator | App och märkning |
| --- | --- |
| Apple Silicon, exempelvis M1, M2 eller M3 | SoftProf - Apple Silicon.app, märkt ARM64 |
| Intel-processor | SoftProf - Intel.app, märkt INTEL |

Kontrollera processorn i **Apple-menyn > Om den här datorn** om du är osäker. Installera en app. ARM64-appen körs direkt utan Rosetta på Apple Silicon; Intel-appen körs direkt på en Intel-Mac. Rosetta används bara i vårt test av Intel-versionen på Apple Silicon.

Bilddialogen börjar på Skrivbordet och ICC-dialogen i `/Library/ColorSync/Profiles`. Därefter kommer de ihåg sina senast valda mappar var för sig.

### Börja med en känd bild

Välj **Öppna bild** och sedan flik. **1 Färgrymder** jämför originalet med vald arbetsfärgrymd. **2 Skrivarprofiler** jämför originalet med en skrivarprofil eller två skrivarprofiler med varandra. För en bild utan profil öppnas en dialog: välj bildens verkliga källprofil eller en egen ICC-fil och klicka **Visa bilden**. Efter Avbryt kan källprofilen väljas i huvudfönstret; källprofilvalet döljs när bilden har inbäddad ICC.

<!-- pipeline -->

Flikarna använder separata vägar: **källprofil > arbetsfärgrymd** respektive **källprofil > skrivarprofil**. Skrivarjämförelsen använder inte arbetsfärgrymden från den andra fliken. En separat visningskonvertering förbereder simuleringen för skärmen; macOS ColorSync anpassar den profilmärkta bilden till aktuell bildskärm.

### Använd rätt fysisk uppsättning

Välj ICC-profil för den verkliga skrivaren, papperet, bläcket och drivrutinsinställningarna. Bildskärmens kalibrering och ljuset där utskriften betraktas påverkar jämförelsen. Soft proof är en profilbaserad uppskattning, inte en mätning eller garanti för en matchande utskrift.

## 2. Profiler och återgivning

### Källprofil och arbetsfärgrymd

I **1 Färgrymder** väljer du **Arbetsfärgrymd**. Färgomfångsfönstret visar källfärg och arbetsfärgrymd. I **2 Skrivarprofiler** väljer du skrivarens och papperets ICC-profil; färgomfångsfönstret visar källfärg och utskriftsfärg.

En inbäddad ICC-profil används alltid som källa. För en bild utan profil väljer du den profil som verkligen beskriver bildens lagrade värden. Denna tilldelade tolkning ändrar inte originalfilen. Fel källprofil ändrar innebörden av alla färger.

Menyn erbjuder sRGB, Adobe RGB (1998), Display P3, ProPhoto RGB och en egen ICC-profil. ProPhoto RGB använder systemprofilen ROMM RGB i macOS. **Behåll bildens färgrymd** undviker en onödig omräkning via arbetsfärgrymd. Återgivningsmetod och svartpunktskompensation gäller konverteringen i aktiv flik. Pappersvitt och trycksvärta finns bara i Skrivarprofiler.

| Återgivningsmetod | Praktisk innebörd |
| --- | --- |
| Relativ kolorimetrisk | Anpassar vitt till målet och mappar färger som ligger utanför dess omfång. |
| Absolut kolorimetrisk | Bevarar absolut kolorimetri, inklusive profilernas vitpunktsförhållande. |
| Perceptuell | Använder profilens perceptuella mappning, om den finns, för att bevara visuella relationer. |

Olika metoder kan ge samma resultat när profilen inte har skilda mappningar.

### Svartpunktskompensation och pappersvitt

**Svartpunktskompensation** anpassar mappningen av mörka toner mellan profiler. Den synliga effekten beror på profilerna och återgivningsmetoden.

**Simulera pappersvitt** är en separat skärminställning. Den väljer absolut kolorimetrisk återgivning från proofprofil till visningsrymd; konverteringsmetoden till skrivaren är ett eget led. Inställningen påverkar förhandsvisningen, inte de sparade skrivarvärdena.

**Simulera trycksvärta** bevarar skrivarprofilens förutsagda svartnivå. Stäng av valet, med pappersvitt avstängt, för att mappa svart till skärmsvart. Pappersvitt aktiverar även trycksvärta. Dessa visningsval ändrar inte exporten. Förhandsvisningen använder samma 8- eller 16-bitars konverteringskedja på nedskalade pixlar, så små detaljer och blandade färger kan avvika från fullupplöst export; LittleCMS optimering är avstängd för att undvika extra interpolationsfel. JPEG-export kan ge ytterligare förändringar.

### Skärmens färghantering

Förhandsvisningen är en ICC-märkt Display P3-bild som visas genom macOS AppKit/ColorSync. Operativsystemet anpassar den till skärmen där fönstret visas, även vid flytt mellan skärmar. Välj inte skärmprofilen som arbets- eller skrivarprofil. Display P3 kan i sig begränsa färger utanför denna mellanliggande visningsrymd.

## 3. Jämför och välj en färg

### Jämförelse sida vid sida

Båda flikarna börjar med originalet till vänster. I Färgrymder visar höger bild vald arbetsfärgrymd; i Skrivarprofiler visar den vald utskriftssimulering. Varje flik behåller sina inställningar när du växlar. I Färgrymder är vänsterbilden alltid originalet. Arbetsfärgrymd, återgivningsmetod och svartpunktskompensation ligger samlade ovanför högerbilden. Bara Skrivarprofiler kan låsa en referens; en ny bild rensar den.

I Färgrymder ändrar du valen ovanför högerbilden och jämför effekten med originalet som alltid ligger till vänster. I Skrivarprofiler använder du **Jämför med annan profil…** för att låsa aktuell simulering och välja en andra skrivarprofil. Referensens bildtext bevarar dess inställningar. **Återställ vänster till original** visar originalbilden till vänster och behåller högerbildens aktuella profil och inställningar.

Bildtexterna visar respektive profil och inställningar. Fortsatta ändringar påverkar höger bild; vänster förblir låst.

I Skrivarprofiler byter **Byt vänster ↔ höger** plats på simuleringarna tillsammans med deras profiler, arbetsfärgrymd, återgivningsmetod, BPC och pappers-/svärtinställningar. Höger sida kan redigeras; vänster förblir låst. Två byten återställer jämförelsens utgångsläge.

### Zoom och rullning

Båda vyerna har gemensam zoom och rullning. **Anpassa** visar hela bilden. Förhandsvisningen skalas ned till högst 1600 pixlar på längsta sidan före ICC-beräkningen. 25 %, 50 % och 100 % använder originalets mått men förstorar den reducerade bilden; de visar inte originalets fulla detaljskärpa. Export och analys av klickade pixlar använder originalbilden.

Nyligen använda förhandsvisningar återanvänds under sessionen (högst sex färdiga lägen). Återgång till ett sparat läge hoppar över avkodning av originalbilden och ICC-beräkning. Originalvyn återanvänds och PNG-komprimeringen är snabbare men fortfarande förlustfri. Nya inställningar beräknas på den nedskalade förhandsvisningen. Export beräknas från originalet i full upplösning.

Knappen **Färgomfång…** ligger direkt under den högra bilden. **Konvertera och spara…** ligger längst till höger på samma rad.

### Klicka för att välja färgprov

Klicka i någon av bildvyerna för att öppna färgomfångsfönstret och följa motsvarande originalpixel. Ett hårkors markerar positionen i båda vyerna. Provet läses ur originalfilen efter eventuell EXIF-orientering, oberoende av zoom.

Klick i en låst referens följer fortfarande originalpixeln genom de **aktuella** profilinställningarna. Referensens gamla konvertering samplas inte. Ändrade inställningar uppdaterar samma valda pixel. En ny bild rensar referensen och färgprovet.

### Läs värdena för varje steg

Färgomfångsfönstret redovisar källvärden och arbetsfärgrymd i första fliken, samt källvärden och förväntade skrivarvärden i den andra. RGB- eller CMYK-värden kan ändras medan Lab-positionen ligger nästan stilla: en färgbevarande konvertering försöker bevara färgen, inte samma tal. En förflyttning visar en beräknad färgändring, exempelvis genom ommappning till annat omfång eller kvantisering.

## 4. Läs färgomfångsdiagrammet

Alla profiler jämförs i **CIELAB D50**. Den vanliga 2D-vyn visar a*/b*-planet ovanifrån. Axelvärdena har samma skala per enhet och utvidgas vid behov utan att krympa när du ändrar inställningar.

<!-- gamut -->

### Konturer, punkter och pilar

Konturerna visar profilerna i aktiv flik. Numrerade punkter och pilar följer **original > arbetsfärgrymd** eller **original > förväntad utskrift**. Dölj konturer var för sig för en tydligare vy. Grå ringar visar föregående inställning för samma pixel.

Sifferraderna visar L*, a*, b*, kanalvärden och **ΔE76 från originalet**. Lab beräknas genom LittleCMS med flyttalsutgång och fast absolut D50-kolorimetri. Kanalomräkningen följer samma 8- eller 16-bitarsflöde som exporten. Skrivarens punkt är profilens förutsägelse, inte en uppmätt utskrift. Skärmprofilen och reglaget för pappersvitssimulering ingår inte i dessa analyskoordinater.

### Ungefärligt färgad bakgrund

**Färgtonad bakgrund** ger en kulörguide; **Styrka** justerar tydligheten. Avmarkera **Följ färgprovets L*** för att välja bakgrundens ljushet från **0 till 100** med reglaget eller sifferfältet (tryck Retur). L* 0 är svart och 100 är vitt. Markera valet för att följa originalprovets L*, eller 65 innan ett prov valts. Bara bakgrunden ändras, inte färgprov, konturer eller export. Bakgrunden är ett färgat snitt vid vald L* bakom de projicerade konturerna, inte en mätning av alla färger i projektionen. Skärmens begränsningar och toningen gör bakgrunden approximativ.

### Konturen är inget exakt omfångstest

Konturerna är konvexa ytterhöljen av samplade ICC-enhetsvärden, projicerade till ett plan. Den tredje dimensionen sammanförs och konkava delar kan överskattas. Samplingen använder 17 nivåer per RGB-/Lab-kanal och 9 per CMYK-kanal, utan separat begränsning av totalfärg i CMYK. En punkt innanför konturen bevisar inte att färgen kan skrivas ut vid sitt L*.

L*, a*, b* och ΔE visas i fasta, linjerade kolumner. Diagrammets ritning hålls inom ramen även vid zoomning och ändrad fönsterstorlek.

## 5. 3D-färgrymd och förflyttning

Välj **Visa 3D-färgrymd**; **Visa 2D** återgår till diagrammet. Välj **Original** och **Arbetsfärgrymd** i första fliken, eller **Original** och **Utskrift** i den andra. Dra för att rotera, rulla för att zooma eller välj **Återställ 3D-vy**. L* ökar uppåt mot ljusare färger, a* går från grönt (negativt) till rött (positivt) och b* från blått (negativt) till gult (positivt). Följ axlarnas märkning när vyn roteras. Bildens valda pixel markeras med en vit ring i valt steg. L*-reglaget för bakgrunden gäller bara 2D.

Markera **Visa förflyttning** för gula pilar. I **Skrivarprofiler** går pilarna alltid **original > förväntad utskrift**, oavsett vilka punkter som visas: pilens början är originalfärgen och spetsen är utskriftsfärgen. I **Färgrymder** jämför pilarna föregående och nya lägen när inställningar eller visat steg ändras. Pappersvitt och trycksvärta ändrar inte absoluta Lab-positioner.

Svaga, tunna pilar visar sällsynta färger; starkare pilar visar vanligare färger i bildens stickprov. Pilens längd visar färgskillnaden, inte förekomsten. Ingen färggrupp döljs av viktningen. Långa pilar kan komma från ett fåtal starkt mättade färger som skrivaren inte kan återge; de betyder inte att större delen av bilden ändras lika mycket.

**Jämför vänster → höger** jämför den låsta vänsterbilden med aktuell högerbild. Punkterna visar alltid högerbildens färger. En gul pil börjar vid motsvarande färgläge i vänsterbilden och slutar vid högerbildens punkt. Små pilspetsar håller punkterna synliga; referensringar visas inte. Den korta bildtexten anger båda profilerna. Byte av bilderna vänder jämförelsen. Återställning av vänsterbilden tar bort referensjämförelsen. Detta är profilernas absoluta D50-färger; skärmens pappers-/svärtsimulering ändrar inte koordinaterna.

3D-vyn visar upp till 1 024 vanliga grupper ur högst 65 536 reproducerbart samplade pixlar. Närliggande källkanalvärden grupperas och en faktisk originalpixel representerar varje grupp. De mindre punkterna gör täta områden tydligare; punktstorleken ökar fortfarande med ungefärlig samplad förekomst; helt genomskinliga pixlar utelämnas och delvis alfa viktar förekomsten. Ovanliga färger kan utelämnas. Punkterna är bildens fördelning, inte ett helt profilomfång eller volymskal. Punkternas Display P3-skärmfärger är approximativa. Originalbilderna ändras inte.

<!-- cloud -->

## 6. Spara och skriv ut

Välj **Konvertera och spara** när en bild och en skrivar-/pappersprofil är valda. Sparande finns i fliken Skrivarprofiler. Appen bearbetar hela originalbilden direkt från källprofilen till högerbildens skrivarprofil och bäddar sedan in vald ICC-fil **byte för byte**. Originalbilden får inte skrivas över. Nya filer följer systemets umask; ersättning av en befintlig export bevarar dess behörighetsbitar. En temporär fil skrivs färdigt innan målfilen ersätts.

| Format | Utkanaler som stöds |
| --- | --- |
| TIFF | RGB, RGBA, CMYK, gråskala, gråskala med alfa, Lab |
| PNG | RGB, RGBA, gråskala, gråskala med alfa |
| JPEG | RGB, CMYK, gråskala; ingen alfa; förstörande komprimering |

En oförenlig kombination av kanaler och format stoppas. Transparens kan bevaras vid RGB- eller gråskalebearbetning; CMYK-/Lab-konvertering med alfa stoppas. Transparenta färgprov analyseras före blandning mot en bakgrund, och alfa redovisas separat.

### Skriv ut de konverterade värdena en gång

Exportbilden är redan konverterad till skrivarprofilen. Skriv ut dessa värden med ytterligare färgkonvertering avstängd i program, operativsystem och drivrutin. Använd samma skrivare, papper, medie- och kvalitetsinställningar som ICC-profilen. Appen exporterar filer; den styr eller verifierar inte drivrutinen eller den fysiska utskriftskedjan.

### Versionens begränsningar

Indexerade PNG-bilder utökas till RGB/RGBA med bevarad ICC-profil och transparens. Appen stöder en bildruta och **8 eller osignerade 16 bitar per kanal**. För 16-bitarsbilder använder RGB/RGBA och gråskala/alfa TIFF eller PNG; CMYK använder TIFF. TIFF stöder okomprimerat, LZW, Deflate/ZIP och PackBits, separata kanalplan och orientering. ICC-konvertering, valda pixlar, 3D-positioner och TIFF/PNG-export bevarar 16-bitars precision. Kanalvärdena går från 0 till 65 535 i stället för 0 till 255. JPEG är bara 8 bitar och kan inte väljas för 16-bitarsoriginal. Filer med 16-bitars Lab och 32-bitars/flyttalsbilder stöds inte; en Lab-arbetsprofil fungerar fortfarande. Export bevarar pixelmått, ICC, DPI och stödd alfa, inte all EXIF/XMP. Pappersvitt och trycksvärta bakas inte in i exporten.

En lyckad export eller en liten förutsagd ΔE visar inte uppmätt utskriftsnoggrannhet. Bedöm viktiga arbeten med en korrekt förberedd fysisk provutskrift.

En numerisk jämförelse med Photoshop 27.11 hittade och rättade ett optimeringsfel i mörka toner. Kvarvarande skillnader redovisas i färgkontrollrapporten på GitHub. Detta verifierar inte Photoshops korrekturvisning på skärmen eller fysisk utskriftsnoggrannhet.

## 7. Språk, arkitektur och licens

### Språk och avslut

Välj **Svenska** eller **English** vid **Språk / Language**. Båda fönstren, menyer, statusmeddelanden och appens egna feltexter uppdateras direkt. Profilval, färgprov och låst referens bevaras. Valet återställs vid nästa start. Profilnamn och filnamn översätts inte; macOS egna knappar och systemfel kan följa systemspråket.

**Avsluta** finns längst ned till höger i huvudfönstret. Du kan även använda appmenyn eller Kommando-Q. Vanlig avslutning väntar tills en pågående export är klar. Vid SIGTERM städar exportprocessen sin temporära fil; tvångsavslutning eller strömavbrott kan inte garantera städning.

### ARM, Intel och Rosetta

Nederst skiljer appen på datorns hårdvara, Python-processens arkitektur och direkt körning respektive Rosetta. Rosetta läses i själva Python-processen. Uppgifter som inte kan fastställas visas som **Okänd**. Klassificeringen av native ARM, native Intel och Rosetta testas; DMG-filen innehåller separata ARM64- och x86_64-appar med strikt kontroll av binärerna. ARM64 testas direkt; Intel testas via Rosetta på Apple Silicon, inte på en fysisk Intel-Mac.

### GPL-licens och kontakt

Copyright (c) 2026 **Christer Törnkvist**.
E-post: **christer@borgasundsfotografiska.se**.

Programmet och dokumentationen är fri programvara under **GNU General Public License, version 3 eller valfri senare version** (GPL-3.0-or-later). De tillhandahålls utan garanti. Den fullständiga, oförändrade licensen finns i **LICENSE**. Tredjepartskod, systemresurser och typsnitt behåller sina egna villkor; se **LICENSE_SCOPE.md** och **THIRD_PARTY_NOTICES.md**.

Appmenyn har **Om SoftProf** med namn, kontakt och licensinformation samt **Visa GPL-licensen** som öppnar hela texten. DMG-filen innehåller appens källkod, byggverktyg och båda handböckerna. README på engelska beskriver källkodsinstallation, tester och hur DMG-paketet byggs om. Personliga fotografier, mätningar och lokala Python-miljöer ingår inte i Git-repositoryn eller källkodsarkivet.

---

GitHub: [chto0703009/SoftProf](https://github.com/chto0703009/SoftProf)
