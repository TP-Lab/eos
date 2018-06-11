#!/usr/bin/env python3

import testUtils

import argparse
import random
import traceback

###############################################################
# Test for different nodes restart scenarios.
# Nodes can be producing or non-producing.
# -p <producing nodes count>
# -c <chain strategy[replay|resync|none]>
# -s <topology>
# -d <delay between nodes startup>
# -v <verbose logging>
# --kill-sig <kill signal [term|kill]>
# --kill-count <enunode instances to kill>
# --dont-kill <Leave cluster running after test finishes>
# --dump-error-details <Upon error print etc/enumivo/node_*/config.ini and var/lib/node_*/stderr.log to stdout>
# --keep-logs <Don't delete var/lib/node_* folders upon test completion>
###############################################################


Print=testUtils.Utils.Print

def errorExit(msg="", errorCode=1):
    Print("ERROR:", msg)
    traceback.print_stack(limit=-1)
    exit(errorCode)

parser = argparse.ArgumentParser()
parser.add_argument("-p", type=int, help="producing nodes count", default=2)
parser.add_argument("-d", type=int, help="delay between nodes startup", default=1)
parser.add_argument("-s", type=str, help="topology", choices=["mesh"], default="mesh")
parser.add_argument("-c", type=str, help="chain strategy",
                    choices=[testUtils.Utils.SyncResyncTag, testUtils.Utils.SyncNoneTag, testUtils.Utils.SyncHardReplayTag],
                    default=testUtils.Utils.SyncResyncTag)
parser.add_argument("--kill-sig", type=str, choices=[testUtils.Utils.SigKillTag, testUtils.Utils.SigTermTag], help="kill signal.",
                    default=testUtils.Utils.SigKillTag)
parser.add_argument("--kill-count", type=int, help="enunode instances to kill", default=-1)
parser.add_argument("-v", help="verbose logging", action='store_true')
parser.add_argument("--leave-running", help="Leave cluster running after test finishes", action='store_true')
parser.add_argument("--dump-error-details",
                    help="Upon error print etc/enumivo/node_*/config.ini and var/lib/node_*/stderr.log to stdout",
                    action='store_true')
parser.add_argument("--keep-logs", help="Don't delete var/lib/node_* folders upon test completion",
                    action='store_true')
parser.add_argument("--clean-run", help="Kill all enunode and enuwallet instances", action='store_true')
parser.add_argument("--p2p-plugin", choices=["net", "bnet"], help="select a p2p plugin to use. Defaults to net.", default="net")

args = parser.parse_args()
pnodes=args.p
topo=args.s
delay=args.d
chainSyncStrategyStr=args.c
debug=args.v
total_nodes = pnodes
killCount=args.kill_count if args.kill_count > 0 else 1
killSignal=args.kill_sig
killEnuInstances= not args.leave_running
dumpErrorDetails=args.dump_error_details
keepLogs=args.keep_logs
killAll=args.clean_run
p2pPlugin=args.p2p_plugin

seed=1
testUtils.Utils.Debug=debug
testSuccessful=False

random.seed(seed) # Use a fixed seed for repeatability.
cluster=testUtils.Cluster(enuwalletd=True)
walletMgr=testUtils.WalletMgr(True)

try:
    cluster.setChainStrategy(chainSyncStrategyStr)
    cluster.setWalletMgr(walletMgr)

    cluster.killall(allInstances=killAll)
    cluster.cleanup()
    walletMgr.killall(allInstances=killAll)
    walletMgr.cleanup()

    Print ("producing nodes: %d, topology: %s, delay between nodes launch(seconds): %d, chain sync strategy: %s" % (
    pnodes, topo, delay, chainSyncStrategyStr))

    Print("Stand up cluster")
    if cluster.launch(pnodes, total_nodes, topo=topo, delay=delay, p2pPlugin=p2pPlugin) is False:
        errorExit("Failed to stand up enu cluster.")

    Print ("Wait for Cluster stabilization")
    # wait for cluster to start producing blocks
    if not cluster.waitOnClusterBlockNumSync(3):
        errorExit("Cluster never stabilized")

    Print("Stand up ENU wallet enuwallet")
    walletMgr.killall(allInstances=killAll)
    walletMgr.cleanup()
    if walletMgr.launch() is False:
        errorExit("Failed to stand up enuwallet.")

    accountsCount=total_nodes
    walletName="MyWallet"
    Print("Creating wallet %s if one doesn't already exist." % walletName)
    wallet=walletMgr.create(walletName)
    if wallet is None:
        errorExit("Failed to create wallet %s" % (walletName))

    Print ("Populate wallet with %d accounts." % (accountsCount))
    if not cluster.populateWallet(accountsCount, wallet):
        errorExit("Wallet initialization failed.")

    defproduceraAccount=cluster.defproduceraAccount
    enumivoAccount=cluster.enumivoAccount

    Print("Importing keys for account %s into wallet %s." % (defproduceraAccount.name, wallet.name))
    if not walletMgr.importKey(defproduceraAccount, wallet):
        errorExit("Failed to import key for account %s" % (defproduceraAccount.name))

    Print("Create accounts.")
    if not cluster.createAccounts(enumivoAccount):
        errorExit("Accounts creation failed.")

    Print("Wait on cluster sync.")
    if not cluster.waitOnClusterSync():
        errorExit("Cluster sync wait failed.")

    Print("Kill %d cluster node instances." % (killCount))
    if cluster.killSomeEnuInstances(killCount, killSignal) is False:
        errorExit("Failed to kill Enu instances")
    Print("enunode instances killed.")

    Print("Spread funds and validate")
    if not cluster.spreadFundsAndValidate(10):
        errorExit("Failed to spread and validate funds.")

    Print("Wait on cluster sync.")
    if not cluster.waitOnClusterSync():
        errorExit("Cluster sync wait failed.")

    Print ("Relaunch dead cluster nodes instances.")
    if cluster.relaunchEnuInstances() is False:
        errorExit("Failed to relaunch Enu instances")
    Print("enunode instances relaunched.")

    Print ("Resyncing cluster nodes.")
    if not cluster.waitOnClusterSync():
        errorExit("Cluster never synchronized")
    Print ("Cluster synched")

    Print("Spread funds and validate")
    if not cluster.spreadFundsAndValidate(10):
        errorExit("Failed to spread and validate funds.")

    Print("Wait on cluster sync.")
    if not cluster.waitOnClusterSync():
        errorExit("Cluster sync wait failed.")

    testSuccessful=True
finally:
    if testSuccessful:
        Print("Test succeeded.")
    else:
        Print("Test failed.")
    if not testSuccessful and dumpErrorDetails:
        cluster.dumpErrorDetails()
        walletMgr.dumpErrorDetails()
        Print("== Errors see above ==")

    if killEnuInstances:
        Print("Shut down the cluster%s" % (" and cleanup." if (testSuccessful and not keepLogs) else "."))
        cluster.killall(allInstances=killAll)
        walletMgr.killall(allInstances=killAll)
        if testSuccessful and not keepLogs:
            Print("Cleanup cluster and wallet data.")
            cluster.cleanup()
            walletMgr.cleanup()

exit(0)
