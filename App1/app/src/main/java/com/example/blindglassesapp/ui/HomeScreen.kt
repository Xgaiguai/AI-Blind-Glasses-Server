package com.example.blindglassesapp.ui

import android.annotation.SuppressLint
import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.ExperimentalFoundationApi
import androidx.compose.foundation.background
import androidx.compose.foundation.combinedClickable
import androidx.compose.foundation.interaction.MutableInteractionSource
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxHeight
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Bluetooth
import androidx.compose.material.icons.filled.BluetoothDisabled
import androidx.compose.material.icons.filled.Settings
import androidx.compose.material.icons.filled.Videocam
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Scaffold
import androidx.compose.material3.SnackbarHost
import androidx.compose.material3.SnackbarHostState
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TopAppBar
import androidx.compose.material3.TopAppBarDefaults
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.draw.shadow
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.semantics.onLongClick
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import com.example.blindglassesapp.BuildConfig
import com.example.blindglassesapp.ble.BleConnectionState
import com.example.blindglassesapp.ui.theme.AppThemePreference
import com.example.blindglassesapp.ui.theme.PrimaryBlue
import com.example.blindglassesapp.viewmodel.MainViewModel

@OptIn(ExperimentalMaterial3Api::class, ExperimentalFoundationApi::class)
@SuppressLint("MissingPermission")
@Composable
fun HomeScreen(
    viewModel: MainViewModel,
    onScanClick: () -> Unit,
    themePreference: AppThemePreference,
    onThemePreferenceChange: (AppThemePreference) -> Unit,
    onMonitorClick: () -> Unit,
    onOpenAccessibility: () -> Unit,
    modifier: Modifier = Modifier,
) {
    // ── 監聽雙鍵觸發盲人模式的 One-off 事件 ──
    LaunchedEffect(Unit) {
        viewModel.openAccessibilityEvent.collect {
            onOpenAccessibility()
        }
    }

    // ── 保留所有原始 ViewModel 狀態與 LaunchedEffect 邏輯 ──
    val bleState by viewModel.bleState.collectAsState()
    val snackbarHostState = remember { SnackbarHostState() }
    var showDeviceSheet by remember { mutableStateOf(false) }
    var showWifiDialog by remember { mutableStateOf(false) }
    var previousBleState by remember { mutableStateOf<BleConnectionState?>(null) }

    LaunchedEffect(bleState) {
        val prev = previousBleState
        previousBleState = bleState
        when (val s = bleState) {
            is BleConnectionState.DevicesFound -> showDeviceSheet = true
            is BleConnectionState.Error -> snackbarHostState.showSnackbar(s.message)
            is BleConnectionState.Disconnected -> {
                when (prev) {
                    is BleConnectionState.Connected ->
                        snackbarHostState.showSnackbar("已斷開連線")
                    is BleConnectionState.Connecting ->
                        snackbarHostState.showSnackbar("連線未完成或已中斷，請再試一次")
                    else -> { /* 例如舊 GATT 晚到、或與 Idle 重複，不誤導為「已斷開」 */ }
                }
            }
            else -> {}
        }
    }

    val isConnected = bleState is BleConnectionState.Connected
    val isLoading = bleState is BleConnectionState.Scanning || bleState is BleConnectionState.Connecting
    val outline = BorderStroke(1.dp, MaterialTheme.colorScheme.outlineVariant)
    val buttonShape = RoundedCornerShape(16.dp)

    Scaffold(
        snackbarHost = { SnackbarHost(snackbarHostState) },
        topBar = {
            TopAppBar(
                title = {
                    Text(
                        text = "導盲眼鏡",
                        style = MaterialTheme.typography.titleMedium,
                    )
                },
                colors = TopAppBarDefaults.topAppBarColors(
                    containerColor = Color.Transparent,
                    titleContentColor = MaterialTheme.colorScheme.onSurface,
                ),
            )
        },
    ) { innerPadding ->
        // ── 全螢幕長按觸發盲人模式 ──
        Box(
            modifier = modifier
                .fillMaxSize()
                .padding(innerPadding)
                .semantics {
                    onLongClick(label = "進入盲人輔助模式") {
                        onOpenAccessibility()
                        true
                    }
                }
                .combinedClickable(
                    indication = null,
                    interactionSource = remember { MutableInteractionSource() },
                    onClick = { /* 不攔截普通點擊 */ },
                    onLongClick = { onOpenAccessibility() },
                ),
        ) {
            Surface(
                modifier = Modifier.fillMaxSize(),
                color = MaterialTheme.colorScheme.background,
            ) {
                Column(
                    modifier = Modifier
                        .fillMaxSize()
                        .padding(start = 24.dp, end = 24.dp, top = 20.dp, bottom = 0.dp),
                    horizontalAlignment = Alignment.CenterHorizontally,
                    verticalArrangement = Arrangement.Center,
                ) {
                    Spacer(Modifier.weight(1f))
                    
                    // ── 連線狀態中樞 Card ──
                    Card(
                        shape = RoundedCornerShape(16.dp),
                        colors = CardDefaults.cardColors(
                            containerColor = if (isConnected)
                                MaterialTheme.colorScheme.surface
                            else
                                MaterialTheme.colorScheme.surfaceVariant.copy(alpha = 0.3f),
                        ),
                        modifier = Modifier.fillMaxWidth(),
                    ) {
                        Column(
                            modifier = Modifier
                                .fillMaxWidth()
                                .padding(top = 32.dp, bottom = 24.dp),
                            horizontalAlignment = Alignment.CenterHorizontally,
                        ) {
                            // 主視覺圖示 (Hero Icon)
                            Box(
                                modifier = Modifier
                                    .size(88.dp)
                                    .clip(CircleShape)
                                    .background(
                                        if (isConnected) MaterialTheme.colorScheme.primaryContainer 
                                        else MaterialTheme.colorScheme.surfaceVariant.copy(alpha = 0.5f)
                                    ),
                                contentAlignment = Alignment.Center
                            ) {
                                Icon(
                                    imageVector = if (isConnected)
                                        Icons.Default.Bluetooth
                                    else
                                        Icons.Default.BluetoothDisabled,
                                    contentDescription = if (isConnected) "已連線" else "未連線",
                                    tint = if (isConnected)
                                        MaterialTheme.colorScheme.onPrimaryContainer
                                    else
                                        MaterialTheme.colorScheme.onSurfaceVariant.copy(alpha = 0.5f),
                                    modifier = Modifier.size(40.dp),
                                )
                            }
                            
                            Spacer(Modifier.height(20.dp))
                            
                            if (isConnected) {
                                val name = (bleState as BleConnectionState.Connected).deviceName
                                Row(
                                    verticalAlignment = Alignment.CenterVertically,
                                ) {
                                    Box(
                                        modifier = Modifier
                                            .size(8.dp)
                                            .clip(CircleShape)
                                            .background(MaterialTheme.colorScheme.primary),
                                    )
                                    Spacer(Modifier.width(8.dp))
                                    Text(
                                        text = "已連線",
                                        style = MaterialTheme.typography.labelMedium,
                                        color = MaterialTheme.colorScheme.primary,
                                    )
                                }
                                Text(
                                    text = name,
                                    style = MaterialTheme.typography.headlineSmall,
                                    fontWeight = FontWeight.Bold,
                                    color = MaterialTheme.colorScheme.onSurface,
                                    modifier = Modifier.padding(top = 8.dp),
                                )
                            } else {
                                Text(
                                    text = "導盲眼鏡未連線",
                                    style = MaterialTheme.typography.titleLarge,
                                    fontWeight = FontWeight.Bold,
                                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                                )
                                Text(
                                    text = "請開啟藍牙並連接您的設備",
                                    style = MaterialTheme.typography.bodyMedium,
                                    color = MaterialTheme.colorScheme.onSurfaceVariant.copy(alpha = 0.7f),
                                    modifier = Modifier.padding(top = 8.dp),
                                )
                            }
                        }

                        // 增加文字區塊與下方漸層按鈕之間的留白 (Negative Space)
                        Spacer(Modifier.height(16.dp))

                        // 將「連接眼鏡 / 中斷連線」Button 整合進卡片底部（漸層效果）
                        Box(
                            modifier = Modifier
                                .fillMaxWidth()
                                .padding(horizontal = 16.dp)
                                .padding(bottom = 16.dp)
                                .height(56.dp)
                                .clip(buttonShape)
                                .background(
                                    brush = Brush.horizontalGradient(
                                        colors = if (!isLoading) listOf(
                                            PrimaryBlue,
                                            PrimaryBlue.copy(alpha = 0.7f),
                                        ) else listOf(
                                            Color.Gray.copy(alpha = 0.4f),
                                            Color.Gray.copy(alpha = 0.3f),
                                        ),
                                    ),
                                )
                                .then(
                                    if (!isLoading) Modifier.combinedClickable(
                                        indication = null,
                                        interactionSource = remember { MutableInteractionSource() },
                                        onClick = {
                                            if (isConnected) viewModel.disconnect()
                                            else onScanClick()
                                        },
                                    ) else Modifier
                                ),
                            contentAlignment = Alignment.Center,
                        ) {
                            Text(
                                text = if (isConnected) "中斷連線" else "連接眼鏡",
                                style = MaterialTheme.typography.titleMedium,
                                fontWeight = FontWeight.Bold,
                                color = Color.White,
                            )
                        }
                    }

                    if (isConnected) {
                        Spacer(Modifier.height(16.dp))
                        OutlinedButton(
                            onClick = { showWifiDialog = true },
                            modifier = Modifier
                                .fillMaxWidth()
                                .height(64.dp),
                            shape = buttonShape,
                        ) {
                            Text(
                                "設定 Wi-Fi",
                                style = MaterialTheme.typography.titleMedium,
                            )
                        }
                    }

                    Spacer(Modifier.weight(1f))

                    // ── 底部手勢提示 Footer Hint (Icon-less Card) ──
                    Surface(
                        modifier = Modifier
                            .fillMaxWidth()
                            .padding(bottom = 16.dp),
                        shape = RoundedCornerShape(24.dp),
                        color = MaterialTheme.colorScheme.surfaceVariant.copy(alpha = 0.4f),
                        contentColor = MaterialTheme.colorScheme.onSurfaceVariant
                    ) {
                        Column(
                            modifier = Modifier.padding(horizontal = 24.dp, vertical = 20.dp),
                            horizontalAlignment = Alignment.CenterHorizontally
                        ) {
                            Text(
                                text = "盲人模式快捷鍵",
                                style = MaterialTheme.typography.labelLarge,
                                fontWeight = FontWeight.Bold,
                                color = MaterialTheme.colorScheme.primary.copy(alpha = 0.8f)
                            )
                            Spacer(Modifier.height(6.dp))
                            Text(
                                text = "同時點按音量加減鍵，或長按螢幕即可快速進入",
                                style = MaterialTheme.typography.bodyMedium,
                                textAlign = androidx.compose.ui.text.style.TextAlign.Center,
                                color = MaterialTheme.colorScheme.onSurfaceVariant.copy(alpha = 0.8f)
                            )
                        }
                    }
                }
            }

            // ── Loading Overlay ──
            if (isLoading) {
                val msg = when (val s = bleState) {
                    is BleConnectionState.Scanning -> "掃描中..."
                    is BleConnectionState.Connecting -> "連線至 ${s.deviceName}..."
                    else -> "載入中..."
                }
                LoadingOverlay(message = msg)
            }
        }
    }

    // ── 保留所有 Dialog / BottomSheet ──
    if (showDeviceSheet && bleState is BleConnectionState.DevicesFound) {
        DeviceListSheet(
            devices = (bleState as BleConnectionState.DevicesFound).devices,
            onDeviceSelected = { device ->
                showDeviceSheet = false
                viewModel.connectDevice(device)
            },
            onDismiss = {
                showDeviceSheet = false
                viewModel.dismissDeviceListResults()
            },
        )
    }

    if (showWifiDialog) {
        WifiSettingDialog(
            viewModel = viewModel,
            onDismiss = { showWifiDialog = false },
        )
    }
}

