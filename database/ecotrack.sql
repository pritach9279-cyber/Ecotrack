-- =====================================================
-- EcoTrack Database Schema
-- Personal Carbon Footprint Monitoring & Smart Reduction System
-- Import this file via phpMyAdmin (XAMPP) or:
--   mysql -u root -p < ecotrack.sql
-- =====================================================

CREATE DATABASE IF NOT EXISTS ecotrack
    CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

USE ecotrack;

-- ---------------------------------------------------
-- TABLE 1: users
-- ---------------------------------------------------
DROP TABLE IF EXISTS users;
CREATE TABLE users (
    id INT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    email VARCHAR(150) NOT NULL UNIQUE,
    password_hash VARCHAR(255) NOT NULL,
    age INT NOT NULL DEFAULT 0,
    date_of_birth DATE NULL,
    city VARCHAR(100) NOT NULL DEFAULT '',
    state VARCHAR(100) NULL,
    country VARCHAR(100) NULL,
    household_size INT NULL,
    occupation VARCHAR(150) NULL,
    transport_mode VARCHAR(50) NOT NULL DEFAULT 'Walking',
    avg_daily_distance DECIMAL(6,2) NOT NULL DEFAULT 0,
    food_pattern ENUM('Vegetarian', 'Mixed') NOT NULL DEFAULT 'Vegetarian',
    avg_electricity DECIMAL(6,2) NOT NULL DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB;

-- ---------------------------------------------------
-- TABLE 2: daily_activities
-- ---------------------------------------------------
DROP TABLE IF EXISTS daily_activities;
CREATE TABLE daily_activities (
    id INT AUTO_INCREMENT PRIMARY KEY,
    user_id INT NOT NULL,
    date DATE NOT NULL,
    transport_type VARCHAR(50) NOT NULL,
    transport_distance DECIMAL(6,2) NOT NULL DEFAULT 0,
    electricity DECIMAL(6,2) NOT NULL DEFAULT 0,
    food_type VARCHAR(50) NOT NULL,
    waste_amount DECIMAL(6,2) NOT NULL DEFAULT 0,
    transport_co2 DECIMAL(8,3) NOT NULL DEFAULT 0,
    electricity_co2 DECIMAL(8,3) NOT NULL DEFAULT 0,
    food_co2 DECIMAL(8,3) NOT NULL DEFAULT 0,
    waste_co2 DECIMAL(8,3) NOT NULL DEFAULT 0,
    total_co2 DECIMAL(8,3) NOT NULL DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY unique_user_date (user_id, date),
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
) ENGINE=InnoDB;

-- ---------------------------------------------------
-- TABLE 3: emission_factors
-- ---------------------------------------------------
DROP TABLE IF EXISTS emission_factors;
CREATE TABLE emission_factors (
    id INT AUTO_INCREMENT PRIMARY KEY,
    category VARCHAR(50) NOT NULL,
    activity_type VARCHAR(50) NOT NULL,
    factor DECIMAL(8,4) NOT NULL,
    unit VARCHAR(30) NOT NULL,
    source VARCHAR(255) NULL,
    region VARCHAR(100) NULL,
    factor_year SMALLINT NULL,
    version VARCHAR(30) NULL,
    effective_date DATE NULL,
    UNIQUE KEY unique_category_activity (category, activity_type)
) ENGINE=InnoDB;

-- ---------------------------------------------------
-- TABLE 4: goals
-- ---------------------------------------------------
DROP TABLE IF EXISTS goals;
CREATE TABLE goals (
    id INT AUTO_INCREMENT PRIMARY KEY,
    user_id INT NOT NULL,
    target_percentage DECIMAL(5,2) NOT NULL,
    baseline_co2 DECIMAL(8,3) NOT NULL DEFAULT 0,
    start_date DATE NOT NULL,
    target_date DATE NOT NULL,
    is_active TINYINT(1) NOT NULL DEFAULT 1,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
) ENGINE=InnoDB;

-- =====================================================
-- SEED DATA: emission_factors
-- (Approximate, India-context, kg CO2e per unit — clearly
--  labelled as ESTIMATES in the application UI)
-- =====================================================

INSERT INTO emission_factors (category, activity_type, factor, unit) VALUES
-- TRANSPORT (kg CO2e per km)
('transport', 'Walking',            0.0000, 'km'),
('transport', 'Bicycle',            0.0000, 'km'),
('transport', 'Electric Vehicle',   0.0200, 'km'),
('transport', 'Train/Metro',        0.0200, 'km'),
('transport', 'Public Bus',         0.0300, 'km'),
('transport', 'CNG Vehicle',        0.1000, 'km'),
('transport', 'Petrol Bike',        0.0500, 'km'),
('transport', 'Petrol Car',         0.1400, 'km'),
('transport', 'Diesel Car',         0.1700, 'km'),

-- ELECTRICITY (kg CO2e per kWh) - Indian grid average
('electricity', 'Grid Electricity', 0.8200, 'kWh'),

-- FOOD (kg CO2e per day, based on daily meal pattern)
('food', 'Vegan',                   1.0000, 'day'),
('food', 'Vegetarian',              1.5000, 'day'),
('food', 'Mixed',                   2.5000, 'day'),
('food', 'High Meat',               3.3000, 'day'),

-- WASTE (kg CO2e per kg of waste generated)
('waste', 'General Waste',          0.5000, 'kg');

-- ---------------------------------------------------
-- TABLE 5: assessments
-- ---------------------------------------------------
CREATE TABLE assessments (
    id INT AUTO_INCREMENT PRIMARY KEY,
    user_id INT NOT NULL,
    answers JSON NOT NULL,
    result JSON NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
) ENGINE=InnoDB;
