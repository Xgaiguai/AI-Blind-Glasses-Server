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
    var showSettingsMenu by remember { mutableStateOf(false) }

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
                        text = "導盲眼鏡 (版本: ${BuildConfig.VERSION_NAME})",
                        style = MaterialTheme.typography.titleMedium,
                    )
                },
                actions = {
                    // 設定圖示 → 點擊展開 DropdownMenu（收納 ThemePreferenceChipRow）
                    Box {
                        IconButton(
                            onClick = { showSettingsMenu = true },
                            modifier = Modifier.size(64.dp),
                        ) {
                            Icon(
                                imageVector = Icons.Default.Settings,
                                contentDescription = "設定",
                            )
                        }
                        ThemeSettingsDropdown(
                            expanded = showSettingsMenu,
                            onDismiss = { showSettingsMenu = false },
                            current = themePreference,
                            onChange = onThemePreferenceChange,
                        )
                    }
                },
                colors = TopAppBarDefaults.topAppBarColors(
                    containerColor = MaterialTheme.colorScheme.surface,
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
                        .padding(horizontal = 24.dp, vertical = 20.dp),
                    horizontalAlignment = Alignment.CenterHorizontally,
                    verticalArrangement = Arrangement.Center,
                ) {
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
                        Row(
                            modifier = Modifier
                                .fillMaxWidth()
                                .padding(horizontal = 20.dp, vertical = 20.dp),
                            verticalAlignment = Alignment.CenterVertically,
                        ) {
                            // 左側藍牙圖示
                            Icon(
                                imageVector = if (isConnected)
                                    Icons.Default.Bluetooth
                                else
                                    Icons.Default.BluetoothDisabled,
                                contentDescription = if (isConnected) "已連線" else "未連線",
                                tint = if (isConnected)
                                    MaterialTheme.colorScheme.secondary
                                else
                                    MaterialTheme.colorScheme.onSurfaceVariant.copy(alpha = 0.5f),
                                modifier = Modifier.size(40.dp),
                            )
                            Spacer(Modifier.width(16.dp))
                            Column(
                                modifier = Modifier.weight(1f),
                            ) {
                                if (isConnected) {
                                    val name = (bleState as BleConnectionState.Connected).deviceName
                                    Row(
                                        verticalAlignment = Alignment.CenterVertically,
                                    ) {
                                        Box(
                                            modifier = Modifier
                                                .size(8.dp)
                                                .clip(CircleShape)
                                                .background(MaterialTheme.colorScheme.secondary),
                                        )
                                        Spacer(Modifier.width(10.dp))
                                        Text(
                                            text = "已連線",
                                            style = MaterialTheme.typography.labelSmall,
                                            color = MaterialTheme.colorScheme.secondary,
                                        )
                                    }
                                    Text(
                                        text = name,
                                        style = MaterialTheme.typography.titleLarge,
                                        color = MaterialTheme.colorScheme.onSurface,
                                        modifier = Modifier.padding(top = 6.dp),
                                    )
                                } else {
                                    Text(
                                        text = "尚未連線",
                                        style = MaterialTheme.typography.titleMedium,
                                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                                    )
                                    Text(
                                        text = "請先掃描並選擇裝置",
                                        style = MaterialTheme.typography.bodyMedium,
                                        color = MaterialTheme.colorScheme.onSurfaceVariant.copy(alpha = 0.7f),
                                        modifier = Modifier.padding(top = 6.dp),
                                    )
                                }
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
                                .shadow(6.dp, buttonShape)
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

                    // ── 次要功能區 ──
                    Spacer(Modifier.height(24.dp))

                    OutlinedButton(
                        onClick = onMonitorClick,
                        modifier = Modifier
                            .fillMaxWidth()
                            .height(64.dp),
                        shape = buttonShape,
                        border = BorderStroke(1.dp, MaterialTheme.colorScheme.outline),
                    ) {
                        Icon(
                            imageVector = Icons.Default.Videocam,
                            contentDescription = null,
                            modifier = Modifier.size(20.dp),
                        )
                        Spacer(Modifier.width(8.dp))
                        Text(
                            text = "即時監看",
                            style = MaterialTheme.typography.titleMedium,
                        )
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

                    // ── 底部手勢提示 Footer Hint ──
                    Text(
                        text = "同時點按實體音量加減鍵，或長按螢幕可進入盲人輔助模式",
                        style = MaterialTheme.typography.bodyMedium,
                        color = Color.White.copy(alpha = 0.7f),
                        textAlign = androidx.compose.ui.text.style.TextAlign.Center,
                        modifier = Modifier.padding(horizontal = 32.dp).padding(bottom = 8.dp),
                    )
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

// ── 設定選單中收納主題切換 ──
@Composable
private fun ThemeSettingsDropdown(
    expanded: Boolean,
    onDismiss: () -> Unit,
    current: AppThemePreference,
    onChange: (AppThemePreference) -> Unit,
) {
    androidx.compose.material3.DropdownMenu(
        expanded = expanded,
        onDismissRequest = onDismiss,
        modifier = Modifier.width(200.dp),
    ) {
        Column(modifier = Modifier.padding(horizontal = 12.dp, vertical = 8.dp)) {
            Text(
                text = "外觀主題",
                style = MaterialTheme.typography.labelMedium,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
                modifier = Modifier.padding(bottom = 8.dp),
            )
            ThemePreferenceChipRow(
                current = current,
                onChange = { pref ->
                    onChange(pref)
                    onDismiss()
                },
                modifier = Modifier.fillMaxWidth(),
            )
        }
    }
}
