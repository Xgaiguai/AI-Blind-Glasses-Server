package com.example.blindglassesapp.ui

import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Visibility
import androidx.compose.material.icons.filled.VisibilityOff
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.FilterChip
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.text.input.VisualTransformation
import androidx.compose.ui.unit.dp
import com.example.blindglassesapp.ble.BleManager
import com.example.blindglassesapp.data.WifiProfile
import com.example.blindglassesapp.data.WifiProfilesStorage
import com.example.blindglassesapp.viewmodel.MainViewModel

@Composable
fun WifiSettingDialog(
    viewModel: MainViewModel,
    onDismiss: () -> Unit,
    modifier: Modifier = Modifier,
) {
    val context = LocalContext.current
    val storage = remember { WifiProfilesStorage(context) }
    var profiles by remember { mutableStateOf(storage.loadAll()) }

    var ssid by remember { mutableStateOf("") }
    var password by remember { mutableStateOf("") }
    var isSending by remember { mutableStateOf(false) }
    var passwordVisible by remember { mutableStateOf(false) }
    var lastError by remember { mutableStateOf<String?>(null) }

    val writeResult by viewModel.writeResult.collectAsState()
    val chipScroll = rememberScrollState()

    // ── 初始載入已存網路 ──
    LaunchedEffect(Unit) {
        profiles = storage.loadAll()
        val first = profiles.firstOrNull()
        if (first != null) {
            ssid = first.ssid
            password = first.password
        }
    }

    // ── BLE 寫入結果監聽 ──
    LaunchedEffect(writeResult) {
        when (val r = writeResult) {
            is BleManager.WriteResult.Success -> {
                isSending = false
                lastError = null
                storage.upsert(WifiProfile(ssid = ssid.trim(), password = password))
                profiles = storage.loadAll()
                viewModel.clearWriteResult()
                onDismiss()
            }
            is BleManager.WriteResult.Failure -> {
                isSending = false
                lastError = r.message
                viewModel.clearWriteResult()
            }
            null -> {}
        }
    }

    // ── 僅儲存到手機 ──
    fun saveToPhoneOnly() {
        if (ssid.isBlank()) {
            lastError = "請先輸入 Wi‑Fi 名稱 (SSID)"
            return
        }
        storage.upsert(WifiProfile(ssid = ssid.trim(), password = password))
        profiles = storage.loadAll()
        lastError = null
    }

    AlertDialog(
        onDismissRequest = { if (!isSending) onDismiss() },
        shape = RoundedCornerShape(24.dp),
        title = { Text("設定 Wi‑Fi") },
        text = {
            Column(
                modifier = modifier
                    .fillMaxWidth()
                    .verticalScroll(rememberScrollState()),
                verticalArrangement = Arrangement.spacedBy(8.dp),
            ) {
                // ── 說明文字 ──
                Text(
                    text = "點選下方已存網路可帶入名稱與密碼；可自行修改。儲存到手機只寫入本機，不會經藍牙傳送。",
                    style = MaterialTheme.typography.bodyMedium,
                    color = MaterialTheme.colorScheme.onSurfaceVariant.copy(alpha = 0.72f),
                )

                // ── 快速選擇（已存網路）──
                if (profiles.isNotEmpty()) {
                    Spacer(Modifier.height(4.dp))
                    Text(
                        text = "快速選擇（已存網路）",
                        style = MaterialTheme.typography.labelLarge,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                    Row(
                        modifier = Modifier
                            .fillMaxWidth()
                            .horizontalScroll(chipScroll),
                        horizontalArrangement = Arrangement.spacedBy(8.dp),
                    ) {
                        profiles.forEach { p ->
                            FilterChip(
                                selected = p.ssid == ssid.trim(),
                                onClick = {
                                    ssid = p.ssid
                                    password = p.password
                                    lastError = null
                                },
                                label = { Text(p.ssid, maxLines = 1) },
                                enabled = !isSending,
                            )
                        }
                    }
                    Spacer(Modifier.height(8.dp)) // 與下方輸入框共計 16.dp 間距
                }

                // ── SSID 輸入框 ──
                OutlinedTextField(
                    value = ssid,
                    onValueChange = {
                        ssid = it
                        lastError = null
                    },
                    label = { Text("Wi‑Fi 名稱 (SSID)") },
                    singleLine = true,
                    enabled = !isSending,
                    shape = RoundedCornerShape(12.dp),
                    modifier = Modifier.fillMaxWidth(),
                )

                // ── 密碼輸入框（含 trailingIcon 顯示/隱藏切換）──
                OutlinedTextField(
                    value = password,
                    onValueChange = {
                        password = it
                        lastError = null
                    },
                    label = { Text("Wi‑Fi 密碼（可留空）") },
                    singleLine = true,
                    enabled = !isSending,
                    shape = RoundedCornerShape(12.dp),
                    modifier = Modifier.fillMaxWidth(),
                    visualTransformation = if (passwordVisible) {
                        VisualTransformation.None
                    } else {
                        PasswordVisualTransformation()
                    },
                    trailingIcon = {
                        val description = if (passwordVisible) "隱藏密碼" else "顯示密碼"
                        IconButton(
                            onClick = { passwordVisible = !passwordVisible },
                            enabled = !isSending,
                            modifier = Modifier.semantics {
                                contentDescription = description
                            },
                        ) {
                            Icon(
                                imageVector = if (passwordVisible) {
                                    Icons.Default.VisibilityOff
                                } else {
                                    Icons.Default.Visibility
                                },
                                contentDescription = description,
                            )
                        }
                    },
                )

                // ── 錯誤訊息 ──
                lastError?.let { err ->
                    Text(
                        text = err,
                        color = MaterialTheme.colorScheme.error,
                        style = MaterialTheme.typography.bodySmall,
                    )
                }

                // ── 傳送中 Loading ──
                if (isSending) {
                    Spacer(Modifier.height(8.dp))
                    CircularProgressIndicator(
                        modifier = Modifier
                            .align(Alignment.CenterHorizontally)
                            .padding(8.dp),
                    )
                }

                // ── 分隔線：區隔主行動與次要管理行動 ──
                Spacer(Modifier.height(4.dp))
                HorizontalDivider(
                    color = MaterialTheme.colorScheme.outlineVariant.copy(alpha = 0.38f),
                )
                Spacer(Modifier.height(4.dp))

                // ── 次要管理按鈕（儲存、移除、清除全部）──
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.spacedBy(4.dp),
                ) {
                    TextButton(
                        onClick = { saveToPhoneOnly() },
                        enabled = !isSending,
                    ) {
                        Text("儲存到手機")
                    }
                    TextButton(
                        onClick = {
                            if (ssid.isNotBlank()) {
                                storage.remove(ssid)
                                profiles = storage.loadAll()
                                if (profiles.isNotEmpty()) {
                                    ssid = profiles.first().ssid
                                    password = profiles.first().password
                                } else {
                                    ssid = ""
                                    password = ""
                                }
                                lastError = null
                            }
                        },
                        enabled = !isSending && ssid.isNotBlank() && profiles.any { it.ssid == ssid.trim() },
                    ) {
                        Text("移除這筆")
                    }
                    TextButton(
                        onClick = {
                            storage.clear()
                            profiles = emptyList()
                            ssid = ""
                            password = ""
                            lastError = null
                        },
                        enabled = !isSending && profiles.isNotEmpty(),
                    ) {
                        Text("清除全部")
                    }
                }
            }
        },
        // ── 主行動按鈕：傳送到眼鏡（實心 Button）──
        confirmButton = {
            Button(
                onClick = {
                    if (ssid.isNotBlank()) {
                        lastError = null
                        isSending = true
                        val ok = viewModel.writeWifiCredentials(ssid.trim(), password)
                        if (!ok) {
                            isSending = false
                            lastError = "無法送出（請確認已連線眼鏡）"
                        }
                    }
                },
                enabled = ssid.isNotBlank() && !isSending,
                shape = RoundedCornerShape(12.dp),
            ) {
                Text("傳送到眼鏡")
            }
        },
        // ── 次要行動按鈕：關閉（TextButton）──
        dismissButton = {
            TextButton(
                onClick = onDismiss,
                enabled = !isSending,
            ) {
                Text("關閉")
            }
        },
    )
}
