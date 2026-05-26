package com.example.blindglassesapp.ui

import android.annotation.SuppressLint
import androidx.compose.foundation.gestures.awaitEachGesture
import androidx.compose.foundation.gestures.awaitFirstDown
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.ui.input.pointer.pointerInput
import kotlinx.coroutines.coroutineScope
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import kotlinx.coroutines.Job
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Accessibility
import androidx.compose.material.icons.filled.Info
import androidx.compose.material.icons.filled.Refresh
import androidx.compose.material.icons.filled.Settings
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.activity.compose.BackHandler
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.example.blindglassesapp.ble.BleConnectionState
import com.example.blindglassesapp.network.FamilyEndpoints
import com.example.blindglassesapp.tts.TtsManager
import com.example.blindglassesapp.viewmodel.MainViewModel

@SuppressLint("MissingPermission")
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun HomeScreen(
    onRequestBleScan: () -> Unit,
    onOpenAccessibility: () -> Unit,
    viewModel: MainViewModel,
    ttsManager: TtsManager,
    hasAnnouncedWelcome: Boolean,
    onWelcomeAnnounced: () -> Unit
) {
    val bleState by viewModel.bleState.collectAsState()
    var showWifiDialog by remember { mutableStateOf(false) }
    var showMonitorScreen by rememberSaveable { mutableStateOf(false) }

    // 用於控制「藍牙連線成功後的 Wi-Fi 對話框」只跳出一次
    var hasAutoOpenedWifiDialog by remember { mutableStateOf(false) }

    // 當連線成功且尚未自動跳出 Wi-Fi 對話框時觸發
    LaunchedEffect(bleState) {
        if (bleState is BleConnectionState.Connected && !hasAutoOpenedWifiDialog) {
            showWifiDialog = true
            hasAutoOpenedWifiDialog = true
        } else if (bleState !is BleConnectionState.Connected) {
            hasAutoOpenedWifiDialog = false
        }
    }

    if (showMonitorScreen) {
        BackHandler {
            showMonitorScreen = false
        }
        MonitorScreen(onBack = { showMonitorScreen = false })
        return
    }

    // 進入首頁時用語音引導盲人 (確保只播報一次)
    LaunchedEffect(Unit) {
        if (!hasAnnouncedWelcome) {
            ttsManager.speak("歡迎使用視障輔助眼鏡。請雙指長按螢幕兩秒鐘，即可進入盲人專用模式。")
            onWelcomeAnnounced()
        }
    }

    Scaffold(
        modifier = Modifier.fillMaxSize().pointerInput(Unit) {
            coroutineScope {
                awaitEachGesture {
                    val down = awaitFirstDown(requireUnconsumed = false)
                    var isTwoFinger = false
                    var job: Job? = null
                    
                    do {
                        val event = awaitPointerEvent()
                        if (event.changes.size >= 2 && !isTwoFinger) {
                            isTwoFinger = true
                            job = launch {
                                delay(2000)
                                ttsManager.speak("正在進入盲人專用模式")
                                onOpenAccessibility()
                            }
                        } else if (event.changes.size < 2 && isTwoFinger) {
                            isTwoFinger = false
                            job?.cancel()
                        }
                    } while (event.changes.any { it.pressed })
                    
                    job?.cancel()
                }
            }
        },
        topBar = {
            TopAppBar(
                title = {
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        Text(
                            text = "視障輔助眼鏡",
                            fontWeight = FontWeight.Bold,
                            fontSize = 20.sp
                        )
                    }
                },
                colors = TopAppBarDefaults.topAppBarColors(
                    containerColor = MaterialTheme.colorScheme.background
                )
            )
        }
    ) { innerPadding ->
        Column(
            modifier = Modifier
                .fillMaxSize()
                .padding(innerPadding)
                .padding(16.dp)
                .verticalScroll(rememberScrollState()),
            verticalArrangement = Arrangement.Top,
            horizontalAlignment = Alignment.CenterHorizontally
        ) {
            // 眼鏡連線卡片
            Card(
                modifier = Modifier
                    .fillMaxWidth()
                    .padding(vertical = 8.dp),
                colors = CardDefaults.cardColors(
                    containerColor = MaterialTheme.colorScheme.surfaceVariant.copy(alpha = 0.5f)
                )
            ) {
                Column(modifier = Modifier.padding(16.dp)) {
                    Text(
                        text = "眼鏡藍牙通訊狀態",
                        style = MaterialTheme.typography.titleMedium,
                        fontWeight = FontWeight.Bold
                    )
                    Spacer(modifier = Modifier.height(8.dp))

                    Row(
                        modifier = Modifier.fillMaxWidth(),
                        horizontalArrangement = Arrangement.SpaceBetween,
                        verticalAlignment = Alignment.CenterVertically
                    ) {
                        val statusText = when (bleState) {
                            is BleConnectionState.Idle -> "未連接"
                            is BleConnectionState.Scanning -> "搜尋眼鏡中..."
                            is BleConnectionState.ScanFinished -> "搜尋完畢"
                            is BleConnectionState.Connecting -> "連線眼鏡中..."
                            is BleConnectionState.Connected -> "眼鏡已連線"
                            is BleConnectionState.Disconnected -> "已中斷連線"
                        }
                        Text(text = "目前狀態: $statusText", style = MaterialTheme.typography.bodyMedium)

                        if (bleState is BleConnectionState.Connected) {
                            Button(
                                onClick = { viewModel.disconnect() },
                                colors = ButtonDefaults.buttonColors(
                                    containerColor = MaterialTheme.colorScheme.error
                                )
                            ) {
                                Text("中斷")
                            }
                        } else {
                            Button(
                                onClick = onRequestBleScan,
                                enabled = bleState !is BleConnectionState.Scanning && bleState !is BleConnectionState.Connecting
                            ) {
                                Text("配對眼鏡")
                            }
                        }
                    }

                    if (bleState is BleConnectionState.Connected) {
                        val device = (bleState as BleConnectionState.Connected).device
                        Spacer(modifier = Modifier.height(8.dp))
                        Text(
                            text = "已連線裝置: ${device.name ?: "未知"} (${device.address})",
                            style = MaterialTheme.typography.bodySmall,
                            color = MaterialTheme.colorScheme.onSurfaceVariant
                        )
                        Spacer(modifier = Modifier.height(12.dp))
                        Button(
                            onClick = { showWifiDialog = true },
                            modifier = Modifier.fillMaxWidth(),
                            colors = ButtonDefaults.buttonColors(
                                containerColor = MaterialTheme.colorScheme.primary
                            )
                        ) {
                            Icon(Icons.Default.Settings, contentDescription = null)
                            Spacer(modifier = Modifier.width(8.dp))
                            Text("設定眼鏡 Wi-Fi")
                        }
                    }
                }
            }

            Spacer(modifier = Modifier.height(8.dp))

            // 家屬監看卡片
            Card(
                modifier = Modifier
                    .fillMaxWidth()
                    .padding(vertical = 8.dp)
            ) {
                Column(modifier = Modifier.padding(16.dp)) {
                    Text(
                        text = "家屬遠端監看",
                        style = MaterialTheme.typography.titleMedium,
                        fontWeight = FontWeight.Bold
                    )
                    Spacer(modifier = Modifier.height(8.dp))
                    Text(
                        text = "當眼鏡已透過 Wi-Fi 連上網路時，家屬可以點擊下方「開啟監看」接收即時影像與狀態。",
                        style = MaterialTheme.typography.bodyMedium,
                        color = MaterialTheme.colorScheme.onSurfaceVariant
                    )
                    Spacer(modifier = Modifier.height(16.dp))
                    Button(
                        onClick = { showMonitorScreen = true },
                        modifier = Modifier.fillMaxWidth()
                    ) {
                        Text("進入遠端監看頁面")
                    }
                    Spacer(modifier = Modifier.height(8.dp))
                    Text(
                        text = "網頁版監看站: ${FamilyEndpoints.MONITOR_PAGE}",
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant
                    )
                }
            }

            Spacer(modifier = Modifier.height(8.dp))

            // 盲人輔助模式入口
            Card(
                modifier = Modifier
                    .fillMaxWidth()
                    .padding(vertical = 8.dp),
                colors = CardDefaults.cardColors(
                    containerColor = MaterialTheme.colorScheme.primaryContainer.copy(alpha = 0.6f)
                )
            ) {
                Column(modifier = Modifier.padding(16.dp)) {
                    Text(
                        text = "盲人輔助模式",
                        style = MaterialTheme.typography.titleMedium,
                        fontWeight = FontWeight.Bold
                    )
                    Spacer(modifier = Modifier.height(8.dp))
                    Text(
                        text = "提供音量調整與找眼鏡功能，並全程語音導引。",
                        style = MaterialTheme.typography.bodyMedium,
                        color = MaterialTheme.colorScheme.onSurfaceVariant
                    )
                    Spacer(modifier = Modifier.height(12.dp))
                    Button(
                        onClick = onOpenAccessibility,
                        modifier = Modifier.fillMaxWidth(),
                        colors = ButtonDefaults.buttonColors(
                            containerColor = MaterialTheme.colorScheme.primary
                        )
                    ) {
                        Icon(Icons.Default.Accessibility, contentDescription = null)
                        Spacer(modifier = Modifier.width(8.dp))
                        Text("進入盲人輔助模式")
                    }
                }
            }

            Spacer(modifier = Modifier.height(8.dp))

            // 主題 preferences 控制組
            Card(
                modifier = Modifier
                    .fillMaxWidth()
                    .padding(vertical = 8.dp)
            ) {
                Column(modifier = Modifier.padding(16.dp)) {
                    ThemePreferenceControls(viewModel = viewModel)
                }
            }

            Spacer(modifier = Modifier.height(16.dp))

            // 底部提示
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.Center,
                verticalAlignment = Alignment.CenterVertically
            ) {
                Icon(
                    imageVector = Icons.Default.Info,
                    contentDescription = null,
                    tint = MaterialTheme.colorScheme.onSurfaceVariant,
                    modifier = Modifier.size(16.dp)
                )
                Spacer(modifier = Modifier.width(4.dp))
                Text(
                    text = "請確保眼鏡已開啟藍牙廣播並處於配對狀態。",
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant
                )
            }
        }
    }

    // 處理藍牙掃描完畢時的底部 BottomSheet 裝置列表
    if (bleState is BleConnectionState.ScanFinished) {
        val listState = bleState as BleConnectionState.ScanFinished
        DeviceListSheet(
            devices = listState.devices,
            onDeviceSelected = { device ->
                viewModel.connectDevice(device)
            },
            onDismiss = {
                viewModel.dismissDeviceListResults()
            }
        )
    }

    // Wi-Fi 憑證輸入對話框
    if (showWifiDialog) {
        WifiSettingDialog(
            viewModel = viewModel,
            onDismiss = { showWifiDialog = false }
        )
    }
}
