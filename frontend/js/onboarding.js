/**
 * Onboarding JavaScript
 * Handles multi-step onboarding process
 */

const APP_CONFIG = window.KINGFLOW_CONFIG || {};
const API_ROOT = (APP_CONFIG.apiBaseUrl || window.location.origin).replace(/\/$/, '');
const API_BASE = `${API_ROOT}/api/v1`;
const accessToken = sessionStorage.getItem('token');
let currentStep = 1;
let logoUploadPending = false;
let onboardingData = {
    barbershopName: '',
    logoFile: null,
    logoUrl: '',
    primaryColor: '#667eea',
    secondaryColor: '#764ba2',
    style: '',
    primaryGoal: '',
    teamSize: 1,
    avgServiceDuration: 30,
    openingTime: '09:00',
    closingTime: '19:00',
    personality: ''
};

// Step navigation
function nextStep(stepNumber) {
    if (currentStep === 2 && logoUploadPending) {
        const status = document.getElementById('logoUploadStatus');
        status.textContent = 'Espera a que termine la subida del logo antes de continuar.';
        return;
    }

    // Validate current step
    if (!validateStep(currentStep)) {
        return;
    }

    // Save current step data
    saveStepData(currentStep);

    // Hide current step
    document.getElementById(`step${currentStep}`).classList.add('hidden');

    // Show next step
    document.getElementById(`step${stepNumber}`).classList.remove('hidden');

    // Update progress bar
    const progress = (stepNumber / 10) * 100;
    document.getElementById('progressBar').style.width = progress + '%';

    currentStep = stepNumber;

    // Send data to backend
    sendStepToBackend(currentStep - 1);
}

function prevStep(stepNumber) {
    // Hide current step
    document.getElementById(`step${currentStep}`).classList.add('hidden');

    // Show previous step
    document.getElementById(`step${stepNumber}`).classList.remove('hidden');

    // Update progress bar
    const progress = (stepNumber / 10) * 100;
    document.getElementById('progressBar').style.width = progress + '%';

    currentStep = stepNumber;
}

// Validate step data
function validateStep(step) {
    switch(step) {
        case 1:
            const name = document.getElementById('barbershopName').value.trim();
            if (!name || name.length < 2) {
                alert('Por favor ingresa el nombre de tu barbería');
                return false;
            }
            return true;
        case 4:
            if (!onboardingData.style) {
                alert('Por favor selecciona el estilo de tu barbería');
                return false;
            }
            return true;
        case 5:
            if (!onboardingData.primaryGoal) {
                alert('Por favor selecciona tu objetivo principal');
                return false;
            }
            return true;
        case 9:
            if (!onboardingData.personality) {
                alert('Por favor selecciona la personalidad de tu negocio');
                return false;
            }
            return true;
        default:
            return true;
    }
}

// Save step data to object
function saveStepData(step) {
    switch(step) {
        case 1:
            onboardingData.barbershopName = document.getElementById('barbershopName').value.trim();
            break;
        case 3:
            onboardingData.primaryColor = document.getElementById('primaryColor').value;
            onboardingData.secondaryColor = document.getElementById('secondaryColor').value;
            break;
        case 6:
            onboardingData.teamSize = parseInt(document.getElementById('teamSize').value);
            break;
        case 7:
            onboardingData.avgServiceDuration = parseInt(document.getElementById('avgDuration').value);
            break;
        case 8:
            onboardingData.openingTime = document.getElementById('openingTime').value;
            onboardingData.closingTime = document.getElementById('closingTime').value;
            break;
    }
}

// Send step data to backend
async function sendStepToBackend(step) {
    if (step === 0) return; // Skip welcome step

    const endpoints = {
        1: '/onboarding/step/1',
        3: '/onboarding/step/3',
        4: '/onboarding/step/4',
        5: '/onboarding/step/5',
        6: '/onboarding/step/6',
        7: '/onboarding/step/7',
        8: '/onboarding/step/8',
        9: '/onboarding/step/9'
    };

    const endpoint = endpoints[step];
    if (!endpoint) return;

    const data = getStepData(step);
    if (!data) return;

    try {
        const response = await KingFlowAuth.fetch(`${API_BASE}${endpoint}`, {
            method: 'POST',
            headers: authHeaders({
                'Content-Type': 'application/json'
            }),
            body: JSON.stringify(data)
        });

        if (response.ok) {
            console.log(`✅ Step ${step} saved to backend`);
        } else {
            console.error(`❌ Failed to save step ${step}`);
        }
    } catch (error) {
        console.error(`Error saving step ${step}:`, error);
    }
}

// Get data for specific step
function getStepData(step) {
    switch(step) {
        case 1:
            return { barbershop_name: onboardingData.barbershopName };
        case 3:
            return {
                primary_color: onboardingData.primaryColor,
                secondary_color: onboardingData.secondaryColor
            };
        case 4:
            return { style: onboardingData.style };
        case 5:
            return { primary_goal: onboardingData.primaryGoal };
        case 6:
            return { team_size: onboardingData.teamSize };
        case 7:
            return { avg_service_duration: onboardingData.avgServiceDuration };
        case 8:
            return {
                opening_time: onboardingData.openingTime,
                closing_time: onboardingData.closingTime
            };
        case 9:
            return { personality: onboardingData.personality };
        default:
            return null;
    }
}

// Radio button selection
function selectRadio(groupName, value) {
    // Remove selected class from all options in group
    const options = document.querySelectorAll(`input[name="${groupName}"]`);
    options.forEach(opt => {
        opt.closest('.radio-option').classList.remove('selected');
    });

    // Add selected class to clicked option
    const selected = document.querySelector(`input[name="${groupName}"][value="${value}"]`);
    if (selected) {
        selected.checked = true;
        selected.closest('.radio-option').classList.add('selected');
    }

    // Save to data object
    if (groupName === 'style') {
        onboardingData.style = value;
    } else if (groupName === 'goal') {
        onboardingData.primaryGoal = value;
    } else if (groupName === 'personality') {
        onboardingData.personality = value;
    }
}

// Color preview update
function updateColorPreview() {
    const primary = document.getElementById('primaryColor').value;
    const secondary = document.getElementById('secondaryColor').value;

    document.getElementById('primaryPreview').style.background = primary;
    document.getElementById('secondaryPreview').style.background = secondary;
}

// Apply color preset
function applyPreset(primary, secondary) {
    document.getElementById('primaryColor').value = primary;
    document.getElementById('secondaryColor').value = secondary;
    updateColorPreview();
}

// Logo preview
function previewLogo(input) {
    if (input.files && input.files[0]) {
        const file = input.files[0];
        const status = document.getElementById('logoUploadStatus');

        if (logoUploadPending) {
            status.textContent = 'Espera a que termine la subida actual antes de seleccionar otro logo.';
            input.value = '';
            return;
        }

        // Validate file size (5MB max)
        if (file.size > 5 * 1024 * 1024) {
            status.textContent = 'El archivo es muy grande. Máximo 5 MB.';
            input.value = '';
            return;
        }

        // Validate file type
        if (!file.type.match('image/(png|jpeg|jpg)')) {
            status.textContent = 'Solo se aceptan archivos PNG o JPG.';
            input.value = '';
            return;
        }

        onboardingData.logoFile = file;

        // Show preview
        const reader = new FileReader();
        reader.onload = function(e) {
            const preview = document.getElementById('logoPreview');
            preview.src = e.target.result;
            preview.classList.remove('hidden');
        };
        reader.readAsDataURL(file);

        // Upload to server
        uploadLogo(file);
    }
}

// Upload logo to server
async function uploadLogo(file) {
    const formData = new FormData();
    formData.append('file', file);
    const status = document.getElementById('logoUploadStatus');
    logoUploadPending = true;
    status.textContent = 'Subiendo logo…';

    try {
        const response = await KingFlowAuth.fetch(`${API_BASE}/onboarding/upload-logo`, {
            method: 'POST',
            headers: authHeaders(),
            body: formData
        });

        if (response.ok) {
            const result = await response.json();
            onboardingData.logoUrl = result.logo_url;
            status.textContent = 'Logo subido correctamente.';
            console.log('✅ Logo uploaded:', result.logo_url);
        } else {
            const result = await response.json().catch(() => ({}));
            status.textContent = result.detail || 'No se pudo subir el logo. Puedes intentarlo otra vez o continuar sin logo.';
            console.error('❌ Failed to upload logo');
        }
    } catch (error) {
        status.textContent = 'No se pudo conectar para subir el logo. Puedes intentarlo otra vez o continuar sin logo.';
        console.error('Error uploading logo:', error);
    } finally {
        logoUploadPending = false;
    }
}

// Drag and drop for logo
const uploadArea = document.getElementById('uploadArea');

uploadArea.addEventListener('dragover', (e) => {
    e.preventDefault();
    uploadArea.classList.add('dragover');
});

uploadArea.addEventListener('dragleave', () => {
    uploadArea.classList.remove('dragover');
});

uploadArea.addEventListener('drop', (e) => {
    e.preventDefault();
    uploadArea.classList.remove('dragover');

    const files = e.dataTransfer.files;
    if (files.length > 0) {
        document.getElementById('logoFile').files = files;
        previewLogo(document.getElementById('logoFile'));
    }
});

// Complete onboarding
async function completeOnboarding() {
    // Validate final step
    if (!validateStep(9)) {
        return;
    }

    // Save final step data
    saveStepData(9);

    // Send final step
    await sendStepToBackend(9);

    // Prepare complete data
    const completeData = {
        barbershop_name: onboardingData.barbershopName,
        primary_color: onboardingData.primaryColor,
        secondary_color: onboardingData.secondaryColor,
        style: onboardingData.style,
        primary_goal: onboardingData.primaryGoal,
        team_size: onboardingData.teamSize,
        avg_service_duration: onboardingData.avgServiceDuration,
        opening_time: onboardingData.openingTime,
        closing_time: onboardingData.closingTime,
        personality: onboardingData.personality,
        logo_uploaded: !!onboardingData.logoUrl
    };

    try {
        // Send complete onboarding data
        const response = await KingFlowAuth.fetch(`${API_BASE}/onboarding/complete`, {
            method: 'POST',
            headers: authHeaders({
                'Content-Type': 'application/json'
            }),
            body: JSON.stringify(completeData)
        });

        if (response.ok) {
            const result = await response.json();
            console.log('✅ Onboarding completed:', result);

            // Save to localStorage
            localStorage.setItem('onboardingCompleted', 'true');
            localStorage.setItem('barbershopProfile', JSON.stringify(result));

            // Show success screen
            document.getElementById('step9').classList.add('hidden');
            document.getElementById('step10').classList.remove('hidden');
            document.getElementById('progressBar').style.width = '100%';
        } else {
            alert('Error al completar el onboarding. Por favor intenta de nuevo.');
        }
    } catch (error) {
        console.error('Error completing onboarding:', error);
        alert('Error de conexión. Por favor intenta de nuevo.');
    }
}

// Go to dashboard
function goToDashboard() {
    window.location.href = '/';
}

// Initialize
if (!accessToken) {
    window.location.replace('/');
}

function authHeaders(extra = {}) {
    return { ...extra, Authorization: `Bearer ${accessToken}` };
}

console.log('🚀 Onboarding initialized');
