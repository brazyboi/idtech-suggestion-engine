CREATE TABLE hardware (
      id SERIAL PRIMARY KEY,
      model_name VARCHAR(255) NOT NULL,
      operate_temperature VARCHAR(100),
      input_power VARCHAR(100),
      ip_rating VARCHAR(50),
      ik_rating VARCHAR(50),
      interface VARCHAR(255),
      extra_specs JSONB,
      is_active BOOLEAN NOT NULL DEFAULT TRUE,
      CONSTRAINT unique_model_name UNIQUE (model_name)
);

-- Create GIN index on extra_specs for efficient JSONB queries
CREATE INDEX idx_hardware_extra_specs ON hardware USING GIN (extra_specs);

CREATE TABLE categories (
    id SERIAL PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    CONSTRAINT unique_category_name UNIQUE (name)
);

CREATE TABLE use_cases (
       id SERIAL PRIMARY KEY,
       name VARCHAR(255) NOT NULL,
       CONSTRAINT unique_use_case_name UNIQUE (name)
);

CREATE TABLE software (
    id SERIAL PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    extra_fields JSONB,
    CONSTRAINT unique_software_name UNIQUE (name)
);

-- Allows many-to-many relationship between hardware and categories
CREATE TABLE hardware_category_map (
       hardware_id INTEGER NOT NULL,
       category_id INTEGER NOT NULL,
       PRIMARY KEY (hardware_id, category_id),
       CONSTRAINT fk_hardware_category_hardware
           FOREIGN KEY (hardware_id)
               REFERENCES hardware(id)
               ON DELETE CASCADE,
       CONSTRAINT fk_hardware_category_category
           FOREIGN KEY (category_id)
               REFERENCES categories(id)
               ON DELETE CASCADE
);

-- Create indexes for efficient lookups
CREATE INDEX idx_hardware_category_map_hardware ON hardware_category_map(hardware_id);
CREATE INDEX idx_hardware_category_map_category ON hardware_category_map(category_id);

-- Allows many-to-many relationship between hardware and use cases
CREATE TABLE hardware_use_case_map (
       hardware_id INTEGER NOT NULL,
       use_case_id INTEGER NOT NULL,
       PRIMARY KEY (hardware_id, use_case_id),
       CONSTRAINT fk_hardware_use_case_hardware
           FOREIGN KEY (hardware_id)
               REFERENCES hardware(id)
               ON DELETE CASCADE,
       CONSTRAINT fk_hardware_use_case_use_case
           FOREIGN KEY (use_case_id)
               REFERENCES use_cases(id)
               ON DELETE CASCADE
);

-- Create indexes for efficient lookups
CREATE INDEX idx_hardware_use_case_map_hardware ON hardware_use_case_map(hardware_id);
CREATE INDEX idx_hardware_use_case_map_use_case ON hardware_use_case_map(use_case_id);

-- Allow many-to-many relationship between hardware and software
CREATE TABLE hardware_software_map (
    hardware_id INTEGER NOT NULL,
    software_id INTEGER NOT NULL,
       PRIMARY KEY (hardware_id, software_id),
       CONSTRAINT fk_hardware_software_hardware
           FOREIGN KEY (hardware_id)
               REFERENCES hardware(id)
               ON DELETE CASCADE,
       CONSTRAINT fk_hardware_software_software
           FOREIGN KEY (software_id)
               REFERENCES software(id)
               ON DELETE CASCADE
);

-- Create indexes for efficient lookups
CREATE INDEX idx_hardware_software_map_hardware ON hardware_software_map(hardware_id);
CREATE INDEX idx_hardware_software_map_software ON hardware_software_map(software_id);