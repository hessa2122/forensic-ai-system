# ForensicAI Corrected System Design

## Correct Level-0 DFD

```mermaid
flowchart LR
  Admin[Admin] --> System[ForensicAI System]
  User[Investigator/Analyst] --> System
  System <--> Users[(Django Users / UserProfile)]
  System <--> Cases[(Cases)]
  System <--> Evidence[(Evidence)]
  System <--> Requests[(Analysis Requests)]
  System <--> Results[(Detection Results)]
  System <--> Recon[(Scene Reconstructions)]
  System <--> Reports[(Reports)]
  System <--> Notifications[(Notifications)]
  System <--> Audit[(Audit Logs)]
  System <--> Settings[(System Settings / Services)]
  System <--> Backups[(Backup Records)]
```

## Correct Level-1 Admin DFD

```mermaid
flowchart TD
  Admin[Admin]
  Admin --> Auth[Authenticate Admin]
  Admin --> Users[Manage Users and Roles]
  Admin --> CasesP[Manage Cases]
  Admin --> RequestsP[Review Analysis Requests]
  Admin --> ResultsP[Monitor Detection Results]
  Admin --> ReconP[Monitor Reconstructions]
  Admin --> ReportsP[Manage Reports]
  Admin --> AuditP[Monitor Audit Logs]
  Admin --> ServicesP[Manage System Services]
  Admin --> BackupP[Create Backups]
  Auth <--> U[(Django Users / UserProfile)]
  Users <--> U
  CasesP <--> C[(Cases)]
  RequestsP <--> AR[(Analysis Requests)]
  ResultsP <--> DR[(Detection Results)]
  ReportsP <--> DR
  ReportsP <--> R[(Reports)]
  ReconP <--> SR[(Scene Reconstructions)]
  AuditP <--> AL[(Audit Logs)]
  ServicesP <--> SS[(System Settings / Services)]
  BackupP <--> BR[(Backup Records)]
```

`View Detection Reports` reads stored Detection Results and Reports, not service toggles.

## Correct Level-1 User DFD

```mermaid
flowchart TD
  User[Investigator/Analyst]
  User --> Register[Register and Login]
  User --> ViewCases[View Assigned Cases]
  User --> Upload[Upload Evidence]
  User --> Submit[Submit Analysis Request]
  User --> Track[Track Request Status]
  User --> ViewResult[View Detection Result]
  User --> Recon[Request/View Reconstruction]
  User --> Notify[Receive Notifications]
  User --> Report[Generate/Download Reports]
  Register <--> U[(Django Users / UserProfile)]
  ViewCases <--> C[(Cases)]
  Upload <--> E[(Evidence)]
  Submit <--> AR[(Analysis Requests)]
  Track <--> AR
  ViewResult <--> DR[(Detection Results)]
  Recon <--> SR[(Scene Reconstructions)]
  Notify <--> N[(Notifications)]
  Report <--> R[(Reports)]
```

`Track Request Status` reads `AnalysisRequest`; there is no separate analysis-status datastore.

## Correct ER Design

```mermaid
erDiagram
  USER ||--|| USER_PROFILE : has
  USER ||--o{ CASE : creates
  USER ||--o{ CASE : assigned
  CASE ||--o{ EVIDENCE : contains
  USER ||--o{ EVIDENCE : uploads
  EVIDENCE ||--o{ ANALYSIS_REQUEST : requests
  ANALYSIS_REQUEST ||--o| DETECTION_RESULT : approves
  EVIDENCE ||--o| DETECTION_RESULT : has
  CASE ||--o{ SCENE_RECONSTRUCTION : has
  EVIDENCE ||--o{ SCENE_RECONSTRUCTION : visualizes
  CASE ||--o{ REPORT : has
  EVIDENCE ||--o{ REPORT : may_include
  DETECTION_RESULT ||--o{ REPORT : may_include
  SCENE_RECONSTRUCTION ||--o{ REPORT : may_include
  USER ||--o{ NOTIFICATION : receives
  USER ||--o{ AUDIT_LOG : causes
  USER ||--o{ BACKUP_RECORD : creates
  SYSTEM_SETTING ||--o{ SYSTEM_SETTING : configures
```

Django's built-in authentication tables provide login and password storage. The application must not add a custom `LOGIN` entity or store plain-text passwords.

## Correct Structural Chart

```text
ForensicAI System
  Admin Module
  User Module
  Case Management Module
  Evidence Management Module
  Analysis Request Module
  AI Detection Module
  3D Reconstruction Module
  Notification Module
  Report Module
  Audit and Backup Module
```

The 3D output from a single image is described as monocular depth-based 2.5D crime-scene visualization using relative scene units unless calibrated multi-view scale data is supplied.
