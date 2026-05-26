package com.example.blindglassesapp.ble

import android.bluetooth.BluetoothDevice

sealed interface BleConnectionState {
    object Idle : BleConnectionState
    object Scanning : BleConnectionState
    data class ScanFinished(val devices: List<BluetoothDevice>) : BleConnectionState
    object Connecting : BleConnectionState
    data class Connected(val device: BluetoothDevice) : BleConnectionState
    data class Disconnected(val reason: String?) : BleConnectionState
}
