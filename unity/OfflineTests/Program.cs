// Entry point: runs every test, or the demo walkthrough with `-- demo`.
// Exit code 0 means every test passed.

using System;

namespace XRPod.VR.OfflineTests
{
    static class Program
    {
        static int Main(string[] args)
        {
            if (args.Length > 0 && args[0] == "demo")
            {
                Demo.Run();
                return 0;
            }

            var failed = 0;
            foreach (var test in Tests.All)
            {
                try
                {
                    test.Run();
                    Console.WriteLine($"  ok    {test.Name}");
                }
                catch (Exception e)
                {
                    failed++;
                    Console.WriteLine($"  FAIL  {test.Name}\n        {e.Message}");
                }
            }

            Console.WriteLine();
            Console.WriteLine(failed == 0
                ? $"All {Tests.All.Length} tests passed."
                : $"{failed} of {Tests.All.Length} tests failed.");
            return failed == 0 ? 0 : 1;
        }
    }
}
