package com.arena.voice.ui.screens

import android.graphics.BitmapFactory
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.Image
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.asImageBitmap
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.hilt.navigation.compose.hiltViewModel
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.arena.voice.api.ApiClient
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.launch
import org.json.JSONObject
import javax.inject.Inject

/**
 * Images / Vision — mirror of the web Images page plus the native sight feature:
 * "Capture & analyze" asks the PC backend to grab and understand its own screen;
 * "Choose image" uploads a photo from the gallery and runs OCR + LLM analysis.
 */
@HiltViewModel
class VisionViewModel @Inject constructor(
    private val api: ApiClient,
) : ViewModel() {
    var ocrText by mutableStateOf("")
        private set
    var analysisText by mutableStateOf("")
        private set
    var busy by mutableStateOf(false)
        private set
    var error by mutableStateOf<String?>(null)
        private set

    fun captureAndAnalyze(promptFocus: String?) {
        busy = true
        error = null
        ocrText = ""
        analysisText = "Beanie is looking at the desktop screen…"
        viewModelScope.launch {
            val raw = api.captureAndAnalyze(promptFocus)
            applyResult(raw, "Desktop screen")
        }
    }

    fun analyzeUpload(bytes: ByteArray, filename: String, mime: String, promptFocus: String?) {
        busy = true
        error = null
        ocrText = ""
        analysisText = "Uploading and analysing…"
        viewModelScope.launch {
            val upload = api.uploadImage(filename, bytes, mime)
            val filePath = upload?.let {
                runCatching { JSONObject(it).optString("file_path") }.getOrNull()
            }.orEmpty()
            if (filePath.isBlank()) {
                error = "Upload failed — is the backend online?"
                busy = false
                return@launch
            }
            val raw = api.analyzeImage(filePath, promptFocus)
            applyResult(raw, filename)
        }
    }

    private fun applyResult(raw: String?, label: String) {
        busy = false
        if (raw == null) {
            error = "No response from backend (offline or missing API key?)."
            return
        }
        runCatching {
            val root = JSONObject(raw)
            if (!root.optBoolean("success", true)) {
                error = root.optString("error", "Analysis failed")
                return
            }
            ocrText = root.optString("ocr_text").ifBlank {
                root.optString("extracted_text").ifBlank { "(no OCR text)" }
            }
            if (root.optBoolean("screen_changed", true) == false && root.has("note")) {
                analysisText = root.optString("note")
            } else {
                analysisText = root.optString("ai_analysis").ifBlank {
                    root.optString("analysis").ifBlank { "(no analysis)" }
                }
            }
        }.onFailure {
            error = "Bad response from backend: ${it.message}"
        }
    }
}

@Composable
fun VisionScreen(viewModel: VisionViewModel = hiltViewModel()) {
    val context = LocalContext.current
    var promptFocus by remember { mutableStateOf("") }
    var preview by remember { mutableStateOf<android.graphics.Bitmap?>(null) }

    val pickImage = rememberLauncherForActivityResult(
        ActivityResultContracts.GetContent()
    ) { uri ->
        if (uri != null) {
            val bytes = runCatching {
                context.contentResolver.openInputStream(uri)?.use { it.readBytes() }
            }.getOrNull()
            if (bytes != null) {
                preview = BitmapFactory.decodeByteArray(bytes, 0, bytes.size)
                val name = "photo.jpg"
                viewModel.analyzeUpload(bytes, name, "image/jpeg", promptFocus.ifBlank { null })
            }
        }
    }

    Column(
        modifier = Modifier
            .fillMaxSize()
            .verticalScroll(rememberScrollState())
            .padding(16.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        Text("Images / Vision", style = MaterialTheme.typography.titleLarge, fontWeight = FontWeight.SemiBold)

        OutlinedTextField(
            value = promptFocus,
            onValueChange = { promptFocus = it },
            label = { Text("What should I focus on? (optional)") },
            singleLine = true,
            modifier = Modifier.fillMaxWidth(),
        )

        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            Button(
                onClick = { viewModel.captureAndAnalyze(promptFocus.ifBlank { null }) },
                enabled = !viewModel.busy,
                modifier = Modifier.weight(1f),
            ) {
                Text("Capture & analyze")
            }
            OutlinedButton(
                onClick = { pickImage.launch("image/*") },
                enabled = !viewModel.busy,
                modifier = Modifier.weight(1f),
            ) {
                Text("Choose image")
            }
        }

        preview?.let { bmp ->
            Image(
                bitmap = bmp.asImageBitmap(),
                contentDescription = "Selected image preview",
                modifier = Modifier
                    .fillMaxWidth()
                    .heightIn(max = 260.dp),
            )
        }

        if (viewModel.busy) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                CircularProgressIndicator(modifier = Modifier.size(18.dp))
                Spacer(Modifier.width(8.dp))
                Text("Beanie is looking…", color = Color(0xFF94A3B8), fontSize = 13.sp)
            }
        }

        viewModel.error?.let { msg ->
            Text("⚠ $msg", color = Color(0xFFEF4444), fontSize = 13.sp)
        }

        Text("OCR text", style = MaterialTheme.typography.labelLarge, color = Color(0xFF94A3B8))
        Surface(
            color = MaterialTheme.colorScheme.surfaceVariant,
            shape = MaterialTheme.shapes.medium,
        ) {
            Text(
                text = viewModel.ocrText.ifBlank { "(nothing yet)" },
                color = Color(0xFFF1F5F9),
                fontSize = 14.sp,
                modifier = Modifier.padding(12.dp),
            )
        }

        Text("AI analysis", style = MaterialTheme.typography.labelLarge, color = Color(0xFF94A3B8))
        Surface(
            color = MaterialTheme.colorScheme.surfaceVariant,
            shape = MaterialTheme.shapes.medium,
        ) {
            Text(
                text = viewModel.analysisText.ifBlank { "(nothing yet)" },
                color = Color(0xFFF1F5F9),
                fontSize = 14.sp,
                modifier = Modifier.padding(12.dp),
            )
        }
    }
}
