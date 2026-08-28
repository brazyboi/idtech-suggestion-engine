# Instructions to test

## Starting PostgreSQL (docker)
```
 docker run -d \
   --name idtech-pg \
   -e POSTGRES_USER=admin \
   -e POSTGRES_PASSWORD=ics1802026 \                                                   
   -e POSTGRES_DB=product_db \         
   -p 5432:5432 \
   postgres:15                                                                                                   
```

## Populating the DB
```
 docker exec -i idtech-pg psql -U admin -d product_db < backend/db_scripts/00_schema.sql                         
 docker exec -i idtech-pg psql -U admin -d product_db < backend/db_scripts/01_insert_categories.sql              
 docker exec -i idtech-pg psql -U admin -d product_db < backend/db_scripts/02_insert_use_cases.sql               
 docker exec -i idtech-pg psql -U admin -d product_db < backend/db_scripts/03_insert_software.sql                
 docker exec -i idtech-pg psql -U admin -d product_db < backend/db_scripts/04_insert_hardware.sql                
 docker exec -i idtech-pg psql -U admin -d product_db < backend/db_scripts/05_insert_c_mappings.sql              
 docker exec -i idtech-pg psql -U admin -d product_db < backend/db_scripts/06_insert_uc_mappings.sql             
 docker exec -i idtech-pg psql -U admin -d product_db < backend/db_scripts/07_insert_sw_mappings.sql             
 docker exec -i idtech-pg psql -U admin -d product_db < backend/db_scripts/09_insert_leads.sql     
```

## Starting the backend
```
 cd backend
 # On Mac/Linux:
 source .venv/bin/activate
 # On Windows
 .venv\Scripts\activate

 uvicorn main:app --reload --host 0.0.0.0 --port 8000     
```

## Starting the frontend
```
cd frontend
npm run dev
```


## Example response to get a recommendation
```
Use case: Parking Payment Systems 
Environment: Outdoor (-20C to 65C) 
Card types: Contact (chip), Contactless (tap), Magstripe (swipe) 
PIN: Yes, PIN required 
Standalone: Host-controlled 
Host interface: RS232 (or USB / Ethernet) 
Display: Yes, display needed
```