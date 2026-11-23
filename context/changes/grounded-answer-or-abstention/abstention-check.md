# Kontrola abstencji: wybór pytania kontrolnego

Data sprawdzenia: 2026-11-23. Korpus: pełna migawka TechQA (`techqa@0b5bbc84b7f07d6d09d063130e90b716d8d4a32a`, zestaw `sections-v1`).
Metoda: `python -m app.cli search "<zapytanie>"` (BM25, k=10, domyślny zestaw fragmentów). Identyfikator fragmentu w tabelach to skrót `doc_id/numer fragmentu`; pełny id ma przedrostek `techqa@0b5bbc84b7f07d6d09d063130e90b716d8d4a32a/sections-v1/`. Wyniki wyszukiwania pochodzą z uruchomienia na lokalnej bazie. Treść dokumentów z top 10 czytano w bazie (tekst dokumentu), nie tylko we fragmentach CLI.

Kryterium: czy wśród pierwszych 10 trafień jest dokument, który odpowiada na pytanie, a nie tylko wspomina o tym samym kodzie błędu lub poleceniu.

## Zapytanie: TRAIN_Q002, pełne pytanie

Treść zapytania:

> Why are replies going to the DLQ with reason 2189 MQRC_CLUSTER_RESOLUTION_ERROR I have changed my cluster receiver to match the IP address used and now I am seeing replies in my DLQ with 2189 MQRC_CLUSTER_RESOLUTION_ERROR. The reply queue is on a different cluster which this qmgr is a member of. The reply message uses replytoqmgr and queue name. The qmgr should see the replytoqmgr in the cluster and get the message over to the queue, but instead goes to dead letter queue. This queue manager is a repository to one cluster and a member of another.

| # | Wynik | Fragment (doc_id/nr) | Tytuł dokumentu |
|---|---|---|---|
| 1 | 168.11 | swg1PM11753/2 | IBM PM11753: RC=2082 (MQRC_UNKNOWN_ALIAS_BASE_Q) RETURNED WHEN A COA MESSAGE IS PUT TO A QALIAS THAT RESOLVES TO A CLUSTERED QUEUE. |
| 2 | 167.47 | swg1PM18426/2 | IBM PM18426: RC=2082 (MQRC_UNKNOWN_ALIAS_BASE_Q) RETURNED WHEN A COA MESSAGE IS PUT TO A QALIAS THAT RESOLVES TO A CLUSTERED QUEUE. |
| 3 | 154.62 | swg1PM11753/1 | IBM PM11753: RC=2082 (MQRC_UNKNOWN_ALIAS_BASE_Q) RETURNED WHEN A COA MESSAGE IS PUT TO A QALIAS THAT RESOLVES TO A CLUSTERED QUEUE. |
| 4 | 151.84 | swg1IT24269/1 | IBM IT24269: Queue manager ceases to participate in cluster after REFRESH CLUSTER. rc=2189 and other errors are seen |
| 5 | 148.83 | swg21229905/0 | IBM WebSphere MQ Clustering - Cluster hints and tips |
| 6 | 148.39 | swg1PM27593/1 | IBM PM27593: CSQT882E FOR REASON 2052 AND CSQX053E ARE RECEIVED WHEN TRYING TO PUT TEMPORARY_DYNAMIC QUEUES THAT ARE LOGICALLY DELETED. |
| 7 | 148.24 | swg1PM18426/1 | IBM PM18426: RC=2082 (MQRC_UNKNOWN_ALIAS_BASE_Q) RETURNED WHEN A COA MESSAGE IS PUT TO A QALIAS THAT RESOLVES TO A CLUSTERED QUEUE. |
| 8 | 147.59 | swg1PI56444/1 | IBM PI56444: MQRC_CONTEXT_HANDLE_ERROR IS RETURNED WRITING ON DLQ, BUT THERE IS NO EVIDENCE OF THIS ERROR IN THE CICS LOG. |
| 9 | 146.39 | swg1PI42870/1 | IBM PI42870: MQRC_CONTEXT_HANDLE_ERROR IS RETURNED WRITING ON DLQ, BUT THERE IS NO EVIDENCE OF THIS ERROR IN THE CICS LOG. |
| 10 | 146.00 | swg1PI48932/1 | IBM PI48932: MQRC_CONTEXT_HANDLE_ERROR IS RETURNED WRITING ON DLQ, BUT THERE IS NO EVIDENCE OF THIS ERROR IN THE CICS LOG. |

## Zapytanie: MQRC_CLUSTER_RESOLUTION_ERROR

| # | Wynik | Fragment (doc_id/nr) | Tytuł dokumentu |
|---|---|---|---|
| 1 | 26.39 | swg21229905/0 | IBM WebSphere MQ Clustering - Cluster hints and tips |
| 2 | 22.06 | swg27048240/45 | IBM Readme for IBM WebSphere MQ for HP NonStop Server, Version 5.3.1, Fix Pack 12 |
| 3 | 21.73 | swg1PM44820/0 | IBM PM44820: WMQ Z/OS 7.0.1: SLOW PROCESSING OF MESSAGES IN THE SYSTEM.CLUSTER.COMMAND.QUEUE |
| 4 | 21.46 | swg21660802/0 | IBM 引起WMQ 集群环境解析错误2189（MQRC_CLUSTER_RESOLUTION_ERROR）的解决方法一例 |
| 5 | 21.45 | swg1IT24269/1 | IBM IT24269: Queue manager ceases to participate in cluster after REFRESH CLUSTER. rc=2189 and other errors are seen |
| 6 | 20.39 | swg1IY66462/1 | IBM IY66462: MESSAGE ON CLUSTER COMMAND QUEUE READ MULTIPLE TIMES |
| 7 | 20.26 | swg1IT20323/3 | IBM IT20323: MQOPEN or MQPUT1 fails with reason code 2189, caused by bad content in qm.ini file. Also FDC with probe RM241000 |
| 8 | 19.58 | swg1PK36884/0 | IBM PK36884: MSG ON CLUSTER CMDQ READ MULTIPLE TIMES |
| 9 | 19.07 | swg1IT24269/2 | IBM IT24269: Queue manager ceases to participate in cluster after REFRESH CLUSTER. rc=2189 and other errors are seen |
| 10 | 18.94 | swg1IZ70611/1 | IBM IZ70611: MQRC_UNKNOWN_OBJECT_NAME returned from MQOPEN/MQPUT1 |

## Zapytanie: 2189

| # | Wynik | Fragment (doc_id/nr) | Tytuł dokumentu |
|---|---|---|---|
| 1 | 14.80 | swg21229905/0 | IBM WebSphere MQ Clustering - Cluster hints and tips |
| 2 | 10.37 | swg1IT20323/3 | IBM IT20323: MQOPEN or MQPUT1 fails with reason code 2189, caused by bad content in qm.ini file. Also FDC with probe RM241000 |
| 3 | 10.04 | swg1IY66462/1 | IBM IY66462: MESSAGE ON CLUSTER COMMAND QUEUE READ MULTIPLE TIMES |
| 4 | 9.88 | swg1PM44820/1 | IBM PM44820: WMQ Z/OS 7.0.1: SLOW PROCESSING OF MESSAGES IN THE SYSTEM.CLUSTER.COMMAND.QUEUE |
| 5 | 9.88 | swg21660802/0 | IBM 引起WMQ 集群环境解析错误2189（MQRC_CLUSTER_RESOLUTION_ERROR）的解决方法一例 |
| 6 | 9.30 | swg1PK36884/0 | IBM PK36884: MSG ON CLUSTER CMDQ READ MULTIPLE TIMES |
| 7 | 8.32 | swg1IT20323/1 | IBM IT20323: MQOPEN or MQPUT1 fails with reason code 2189, caused by bad content in qm.ini file. Also FDC with probe RM241000 |
| 8 | 8.11 | swg1PM44820/0 | IBM PM44820: WMQ Z/OS 7.0.1: SLOW PROCESSING OF MESSAGES IN THE SYSTEM.CLUSTER.COMMAND.QUEUE |
| 9 | 7.91 | swg1IT24269/1 | IBM IT24269: Queue manager ceases to participate in cluster after REFRESH CLUSTER. rc=2189 and other errors are seen |
| 10 | 7.91 | swg1PK66962/1 | IBM PK66962: A 10-SECOND DELAY THAT CAN OCCUR WHEN A PARTIAL REPOSITORY LOOKS FOR A NON-EXISTENT QUEUE DIFFERS BETWEEN Z/OS AND DISTRIBUTED |

## Zapytanie: Makieta 1C, pełne pytanie

Treść zapytania:

> After setting variables with `streamtool setproperty --application-ev` in Streams, do I need to restart the DB2 server that the database toolkit connects to?

| # | Wynik | Fragment (doc_id/nr) | Tytuł dokumentu |
|---|---|---|---|
| 1 | 58.54 | swg21996508/0 | IBM STREAMS 4.1.1.1 and 4.1.1.2  JOBS DO NOT INHERIT THE ENVIRONMENT VARIABLES SET IN .BASHRC, WHEN STREAMS IS RUN AS A SYSTEM SERVICE |
| 2 | 50.22 | swg21993198/2 | IBM Debugging java OutOfMemory issues with Streams Applications |
| 3 | 49.04 | swg1IT18432/0 | IBM IT18432: STREAMS JOBS DO NOT INHERIT THE ENVIRONMENT VARIABLES SET IN .BASHRC, WHEN RUN AS A SYSTEM SERVICE. |
| 4 | 47.72 | swg21993198/1 | IBM Debugging java OutOfMemory issues with Streams Applications |
| 5 | 37.45 | swg21993598/0 | IBM How to collect debug information for CORBA errors? |
| 6 | 32.04 | swg27038498/1 | IBM Using a Teradata database with InfoSphere Streams ODBC operators |
| 7 | 31.00 | swg21993387/2 | IBM Not all Streams resources upgraded on RedHat 6.  Workaround available. |
| 8 | 27.86 | swg21981354/0 | IBM Processing Elements Listed as Unhealthy after Restart or Relocation. |
| 9 | 27.82 | swg21999967/1 | IBM Improve overall Streams performance on upgrade by clearing java class cache |
| 10 | 27.54 | swg1IC96939/1 | IBM IC96939: IOPM - CONFIGURING A DATABASE FOR MONITORING MAY FAIL WITH "UNABLE TO CREATE TABLE: DB2PM_##.EV_LOCK, SQLCODE=-204,SQL |

## Zapytanie: streamtool setproperty

| # | Wynik | Fragment (doc_id/nr) | Tytuł dokumentu |
|---|---|---|---|
| 1 | 27.61 | swg21993198/2 | IBM Debugging java OutOfMemory issues with Streams Applications |
| 2 | 20.72 | swg21993598/0 | IBM How to collect debug information for CORBA errors? |
| 3 | 20.53 | swg21993198/1 | IBM Debugging java OutOfMemory issues with Streams Applications |
| 4 | 18.92 | swg21996508/0 | IBM STREAMS 4.1.1.1 and 4.1.1.2  JOBS DO NOT INHERIT THE ENVIRONMENT VARIABLES SET IN .BASHRC, WHEN STREAMS IS RUN AS A SYSTEM SERVICE |
| 5 | 15.27 | swg1JR57094/3 | IBM JR57094: POLICY SETS OR POLICY BINDINGS WON'T OPEN DURING DEVELOPMENT, AT RUN TIME, OR BOTH AND YOU RECEIVE AN EXCEPTION |
| 6 | 15.01 | swg21418646/3 | IBM Ruleset updates and programmatic notification of RES eXecution Unit |
| 7 | 14.93 | swg1IT18432/0 | IBM IT18432: STREAMS JOBS DO NOT INHERIT THE ENVIRONMENT VARIABLES SET IN .BASHRC, WHEN RUN AS A SYSTEM SERVICE. |
| 8 | 13.47 | swg21999967/2 | IBM Improve overall Streams performance on upgrade by clearing java class cache |
| 9 | 12.63 | swg21664205/1 | IBM Removing highlighting of query terms in the search results of IBM Content Analytics with Enterprise Search |
| 10 | 12.54 | swg21993387/2 | IBM Not all Streams resources upgraded on RedHat 6.  Workaround available. |

## Zapytanie: application-ev

| # | Wynik | Fragment (doc_id/nr) | Tytuł dokumentu |
|---|---|---|---|
| 1 | 15.71 | swg21993198/2 | IBM Debugging java OutOfMemory issues with Streams Applications |
| 2 | 14.87 | swg1IC96939/1 | IBM IC96939: IOPM - CONFIGURING A DATABASE FOR MONITORING MAY FAIL WITH "UNABLE TO CREATE TABLE: DB2PM_##.EV_LOCK, SQLCODE=-204,SQL |
| 3 | 14.51 | swg1ZZ00593/2 | IBM ZZ00593: IMPORT_HEAT.SH IMPROVEMENTS |
| 4 | 12.29 | swg21990930/3 | IBM Attempts to install AppScan Source on Linux results in "Graphical installers not supported" |
| 5 | 11.79 | swg21634811/2 | IBM Indexing Properties that exceed the index size limit when using Force Case-Insensitive Search on IBM FileNet Content Manager for DB2 LUW |
| 6 | 11.76 | swg21993198/1 | IBM Debugging java OutOfMemory issues with Streams Applications |
| 7 | 11.20 | swg1PM90451/0 | IBM PM90451: THE SQL STATEMENT GENERATE BY DATABASE WIZARD IS INCORRENT WHEN USE C&DS EV DRIVER |
| 8 | 10.79 | swg1JR46774/2 | IBM JR46774: MULTIPLE JAVASCRIPTRUNNER EXCEPTIONS IN LOGS CAUSING TIMING ISSUES |
| 9 | 10.59 | swg1ZZ00593/1 | IBM ZZ00593: IMPORT_HEAT.SH IMPROVEMENTS |
| 10 | 10.41 | swg21124218/1 | IBM How to configure a time-out session for idle views |

## Odczyt dokumentów

TRAIN_Q002 (pytanie o odpowiedzi trafiające do DLQ z kodem 2189 po zmianie odbiornika klastra na adres IP; kolejka odpowiedzi w innym klastrze; menedżer kolejek jest repozytorium jednego klastra i członkiem drugiego):

- `swg1IT20323`: kod 2189 z powodu błędnej składni w `qm.ini` (sekcje CHANNELS lub SSL) po restarcie menedżera kolejek. Inna przyczyna niż w pytaniu, brak mowy o adresie IP, replytoqmgr, DLQ ani dwóch klastrach.
- `swg1IT24269`: kod 2189 po `REFRESH CLUSTER` przy zaległych komunikatach na `SYSTEM.CLUSTER.TRANSMIT.QUEUE` i zawieszonych partiach. Inna przyczyna, nie dotyczy zmiany adresu odbiornika.
- `swg21660802` (po chińsku): kod 2189 przy częściowym repozytorium ręcznie zdefiniowanym jako cel `CLUSSDR` z pełnego repozytorium. Inna przyczyna; nie dotyczy odpowiedzi kierowanych przez replytoqmgr do drugiego klastra.
- `swg21229905` (Cluster hints and tips): ogólne porady, kod 2189 występuje tylko w słowach kluczowych; nie wyjaśnia błędu.
- Pozostałe trafienia (`swg1PM11753`, `swg1PM18426`: RC=2082, `swg1PM27593`: 2052, `swg1PI56444`, `swg1PI42870`, `swg1PI48932`: MQRC_CONTEXT_HANDLE_ERROR, `swg1PM44820`, `swg1IY66462`, `swg1PK36884`, `swg1PK66962`, `swg1IZ70611`) dotyczą innych kodów lub innych objawów (tytuły w tabelach). Nie czytano ich w całości; tytuły wskazują inny błąd niż 2189 w opisanym scenariuszu.

Makieta 1C (pytanie, czy po `streamtool setproperty --application-ev` trzeba restartować serwer DB2, z którym łączy się toolkit bazodanowy):

- `swg21996508` (trafienie 1 dla pełnego pytania): w Streams 4.1.1.1 i 4.1.1.2 zadania nie dziedziczą zmiennych z `.bashrc`; obejściem jest `streamtool setproperty ... --application-ev <ZMIENNA>=<WARTOŚĆ>`. Przykładem błędu toolkitu bazodanowego jest brak `ODBCINI` (SQL state 08003). Dokument nie wspomina o restarcie serwera DB2 ani o jego braku.
- `swg1IT18432`: ten sam problem jako APAR (poprawka w 4.1.1.3, lokalne obejście to samo polecenie). Również bez informacji o restarcie DB2.
- `swg21993198`: polecenie `streamtool setproperty --application-ev` użyte do ustawienia ścieżek zrzutów Javy i IBM_JAVA_OPTIONS; temat OutOfMemory, bez związku z DB2.
- Pozostałe trafienia dotyczą innych tematów (tytuły w tabelach).

## Wniosek

- TRAIN_Q002: w top 10 dla pełnego pytania i dla `MQRC_CLUSTER_RESOLUTION_ERROR` oraz `2189` są dokumenty o kodzie 2189, ale żaden nie opisuje przyczyny z pytania (zmiana odbiornika klastra na adres IP, odpowiedzi do innego klastra przez replytoqmgr, menedżer kolejek w dwóch klastrach). Zapytania `MQRC_CLUSTER_RESOLUTION_ERROR` i `2189` zwracają wyłącznie dokumenty o innych przyczynach lub ogólne. Nie ma w top 10 dokumentu odpowiadającego na to pytanie.
- Makieta 1C: temat (zmienne środowiskowe `--application-ev` i toolkit bazodanowy) jest w korpusie obecny (`swg21996508`, `swg1IT18432`), ale pytanie o restart serwera DB2 nie ma w top 10 dokumentu, który na nie odpowiada wprost. To rozstrzygnięcie wymaga oceny człowieka; dokument dotyczy tego samego polecenia i toolkitu, ale nie odpowiada na pytanie o restart.
- Zgodnie z regułą z planu (zmiana kontroli abstencji tylko, gdy w top 10 jest dokument opisujący błąd z TRAIN_Q002) kontrolą abstencji pozostaje TRAIN_Q002. Pytanie z makiety 1C nie nadaje się na kontrolę abstencji, bo jego temat jest w korpusie.

Pytanie kontrolne (dosłownie):

```
Why are replies going to the DLQ with reason 2189 MQRC_CLUSTER_RESOLUTION_ERROR

I have changed my cluster receiver to match the IP address used and now I am seeing replies in my DLQ with 2189 MQRC_CLUSTER_RESOLUTION_ERROR. The reply queue is on a different cluster which this qmgr is a member of. The reply message uses replytoqmgr and queue name. The qmgr should see the replytoqmgr in the cluster and get the message over to the queue, but instead goes to dead letter queue. This queue manager is a repository to one cluster and a member of another. 
```
