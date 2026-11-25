import os, win32com.client
d = os.path.dirname(os.path.abspath(__file__))
w = win32com.client.DispatchEx("Word.Application"); w.Visible = False
doc = w.Documents.Open(os.path.join(d, "REPORT_Network_Fault_Prediction_RCA.docx"))
doc.ExportAsFixedFormat(os.path.join(d, "REPORT_Network_Fault_Prediction_RCA.pdf"), 17)
print("pages", doc.ComputeStatistics(2)); doc.Close(False); w.Quit()
